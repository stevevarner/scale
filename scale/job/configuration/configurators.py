"""Defines the classes that handle processing job and execution configuration"""
from __future__ import unicode_literals

import math
import os

from django.conf import settings

from job.configuration.docker_param import DockerParameter
from job.configuration.input_file import InputFile
from job.configuration.json.execution.exe_config import ExecutionConfiguration
from job.configuration.volume import Volume, MODE_RO, MODE_RW
from job.configuration.workspace import TaskWorkspace
from job.execution.container import get_job_exe_input_vol_name, get_job_exe_output_vol_name, get_mount_volume_name, \
    get_workspace_volume_name, SCALE_JOB_EXE_INPUT_PATH, SCALE_JOB_EXE_OUTPUT_PATH
from job.tasks.pull_task import create_pull_command
from node.resources.node_resources import NodeResources
from node.resources.resource import Disk
from storage.container import get_workspace_volume_path
from storage.models import Workspace
from scheduler.vault.manager import secrets_mgr


def normalize_env_var_name(name):
    """Returns a normalized version of the given string name so it can be used as the name of an environment variable

    :param name: The string name to normalize
    :type name: string
    :returns: The normalized environment variable name
    :rtype: string
    """

    return name.replace('-', '_').upper()


class QueuedExecutionConfigurator(object):
    """Configurator that creates execution configurations when a job execution is queued
    """

    def __init__(self, input_files):
        """Creates a QueuedExecutionConfigurator for a set of input files. Each scale_file model must have its related
        workspace field populated.

        :param input_files: The dict of scale_file models stored by ID
        :type input_files: dict
        """

        self._input_files = input_files
        self._cached_workspace_names = {}  # {ID: Name}

    def configure_queued_job(self, job):
        """Creates and returns an execution configuration for the given queued job. The given job model should have its
        related job_type and job_type_rev models populated.

        :param job: The queued job model
        :type job: :class:`job.models.Job`
        :returns: The execution configuration for the queued job
        :rtype: :class:`job.configuration.json.execution.exe_config.ExecutionConfiguration`
        """

        config = ExecutionConfiguration()
        data = job.get_job_data()

        # Add input file meta-data
        input_files_dict = self._create_input_file_dict(data)
        config.set_input_files(input_files_dict)

        # Set up env vars for job's input data
        env_vars = {}
        # TODO: refactor this to use JobData method after Seed upgrade
        for data_input in data.get_dict()['input_data']:
            input_name = data_input['name']
            env_var_name = normalize_env_var_name(input_name)
            if 'value' in data_input:
                env_vars[env_var_name] = data_input['value']
            if 'file_id' in data_input:
                input_file = input_files_dict[input_name][0]
                file_name = os.path.basename(input_file.workspace_path)
                if input_file.local_file_name:
                    file_name = input_file.local_file_name
                env_vars[env_var_name] = os.path.join(SCALE_JOB_EXE_INPUT_PATH, input_name, file_name)
            elif 'file_ids' in data_input:
                env_vars[env_var_name] = os.path.join(SCALE_JOB_EXE_INPUT_PATH, input_name)

        task_workspaces = {}
        if job.job_type.is_system:
            # Add any workspaces needed for this system job
            task_workspaces = QueuedExecutionConfigurator._system_job_workspaces(job)
        else:
            # Set any output workspaces needed
            # TODO: In the future, output workspaces can be moved from job data to configuration, moving this step to
            # the ScheduledExecutionConfigurator
            self._cache_workspace_names(data.get_output_workspace_ids())
            output_workspaces = {}
            for output, workspace_id in data.get_output_workspaces().items():
                output_workspaces[output] = self._cached_workspace_names[workspace_id]
            config.set_output_workspaces(output_workspaces)

        # Create main task with fields populated from input data
        config.create_tasks(['main'])
        config.add_to_task('main', args=job.get_job_interface().get_command_args(), env_vars=env_vars,
                           workspaces=task_workspaces)
        return config

    def _cache_workspace_names(self, workspace_ids):
        """Queries and caches the workspace names for the given IDs

        :param workspace_ids: The set of workspace IDs
        :type workspace_ids: set
        """

        ids = []
        for workspace_id in workspace_ids:
            if workspace_id not in self._cached_workspace_names:
                ids.append(workspace_id)

        if ids:
            for workspace in Workspace.objects.filter(id__in=ids).iterator():
                self._cached_workspace_names[workspace.id] = workspace.name

    def _create_input_file_dict(self, job_data):
        """Creates the dict storing lists of input files by input name

        :param job_data: The job data
        :type job_data: :class:`job.configuration.data.job_data.JobData`
        :returns: A dict where input name maps to lists of input files
        :rtype: dict
        """

        files_dict = {}

        for input_name, file_ids in job_data.get_input_file_ids_by_input().items():
            file_list = []
            file_names = set()
            for file_id in file_ids:
                scale_file_model = self._input_files[file_id]
                input_file = InputFile(scale_file_model)
                # Check for file name collision and use Scale file ID to ensure names are unique
                file_name = scale_file_model.file_name
                if file_name in file_names:
                    file_name = '%d.%s' % (scale_file_model.id, file_name)
                    input_file.local_file_name = file_name
                file_names.add(file_name)
                file_list.append(input_file)
            files_dict[input_name] = file_list

        return files_dict

    @staticmethod
    def _system_job_workspaces(job):
        """Returns any workspaces needed for the main task if this job is a system job. The given job model should have
        its related job_type and job_type_rev models populated.

        :param job: The queued job model
        :type job: :class:`job.models.Job`
        :returns: A dict where workspaces are stored by name
        :rtype: dict
        """

        workspaces = {}
        data = job.get_job_data()

        # Configure ingest workspace based on input data values
        if job.job_type.name == 'scale-ingest':
            workspace_name = None
            new_workspace_name = None
            prop_dict = data.get_property_values(['Ingest ID', 'workspace', 'new_workspace'])
            if 'workspace' in prop_dict:
                workspace_name = prop_dict['workspace']
                if 'new_workspace' in prop_dict:
                    new_workspace_name = prop_dict['new_workspace']
            else:
                # Old ingest jobs do not have the workspace(s) in their data, will need to query ingest model
                if 'Ingest ID' in prop_dict:
                    ingest_id = int(prop_dict['Ingest ID'])
                    from ingest.models import Ingest
                    ingest = Ingest.objects.select_related('workspace', 'new_workspace').get(id=ingest_id)
                    workspace_name = ingest.workspace.name
                    new_workspace_name = ingest.new_workspace.name
            if workspace_name:
                workspaces[workspace_name] = TaskWorkspace(workspace_name, MODE_RW)
            if new_workspace_name:
                workspaces[new_workspace_name] = TaskWorkspace(new_workspace_name, MODE_RW)

        # Configure Strike workspace based on current configuration
        if job.job_type.name == 'scale-strike':
            from ingest.models import Strike
            strike = Strike.objects.get(job_id=job.id)
            workspace_name = strike.get_strike_configuration().get_workspace()
            workspaces[workspace_name] = TaskWorkspace(workspace_name, MODE_RW)

        # Configure Scan workspace based on current configuration
        if job.job_type.name == 'scale-scan':
            from ingest.models import Scan
            try:
                scan = Scan.objects.get(job_id=job.id)
            except Scan.DoesNotExist:
                scan = Scan.objects.get(dry_run_job_id=job.id)
            workspace_name = scan.get_scan_configuration().get_workspace()
            workspaces[workspace_name] = TaskWorkspace(workspace_name, MODE_RW)

        return workspaces


class ScheduledExecutionConfigurator(object):
    """Configurator that handles execution configurations when a job execution is scheduled
    """

    def __init__(self, workspaces):
        """Creates a ScheduledExecutionConfigurator

        :param workspaces: The dict of workspace models stored by name
        :type workspaces: dict
        """

        self._workspaces = workspaces

        db = settings.DATABASES['default']
        self._system_settings = {'SCALE_DB_NAME': db['NAME'], 'SCALE_DB_USER': db['USER'],
                                 'SCALE_DB_PASS': db['PASSWORD'], 'SCALE_DB_HOST': db['HOST'],
                                 'SCALE_DB_PORT': db['PORT']}
        self._system_settings_hidden = {key: '*****' for key in self._system_settings.keys()}

    def configure_scheduled_job(self, job_exe, job_type, interface):
        """Configures the JSON configuration field for the given scheduled job execution. The given job_exe and job_type
        models will not have any related fields populated. The execution configuration in the job_exe model will have
        all secret values replaced with '*****' so that it is safe to be stored in the database. Another copy of this
        configuration will be returned that has the actual secret values populated and can be used for actual
        scheduling.

        :param job_exe: The job execution model being scheduled
        :type job_exe: :class:`job.models.JobExecution`
        :param job_type: The job type model
        :type job_type: :class:`job.models.JobType`
        :param interface: The job interface
        :type interface: :class:`job.configuration.interface.job_interface.JobInterface`
        :returns: A copy of the configuration containing secret values
        :rtype: :class:`job.configuration.json.execution.exe_config.ExecutionConfiguration`
        """

        config = job_exe.get_execution_configuration()

        # Configure items specific to the main task
        ScheduledExecutionConfigurator._configure_main_task(config, job_exe, job_type, interface)

        # Configure job tasks based upon whether system job or regular job
        if job_type.is_system:
            ScheduledExecutionConfigurator._configure_system_job(config, job_exe)
        else:
            ScheduledExecutionConfigurator._configure_regular_job(config, job_exe)

        # Configure items that apply to all tasks
        self._configure_all_tasks(config, job_exe)

        # Configure secrets
        config_with_secrets = self._configure_secrets(config, job_exe, job_type, interface)

        job_exe.configuration = config.get_dict()
        return config_with_secrets

    def _configure_all_tasks(self, config, job_exe):
        """Configures the given execution with items that apply to all tasks

        :param config: The execution configuration
        :type config: :class:`job.configuration.json.execution.exe_config.ExecutionConfiguration`
        :param job_exe: The job execution model being scheduled
        :type job_exe: :class:`job.models.JobExecution`
        """

        config.set_task_ids(job_exe.get_cluster_id())

        # Configure env vars describing allocated task resources
        for task_type in config.get_task_types():
            # Configure env vars describing allocated task resources
            env_vars = {}
            resources_json = config.get_resources(task_type).get_json()
            for name, value in resources_json.get_dict().items():
                env_name = 'ALLOCATED_%s' % normalize_env_var_name(name)
                env_vars[env_name] = value

            # Configure workspace volumes
            workspace_volumes = {}
            for task_workspace in config.get_workspaces(task_type):
                workspace_model = self._workspaces[task_workspace.name]
                # TODO: Should refactor workspace broker to return a Volume object and remove BrokerVolume
                if workspace_model.volume:
                    vol_name = get_workspace_volume_name(job_exe, task_workspace.name)
                    cont_path = get_workspace_volume_path(vol_name)
                    if workspace_model.volume.host:
                        host_path = workspace_model.volume.remote_path
                        volume = Volume(vol_name, cont_path, task_workspace.mode, is_host=True, host_path=host_path)
                    else:
                        driver = workspace_model.volume.driver
                        driver_opts = {}
                        # TODO: Hack alert for nfs broker, as stated above, we should return Volume from broker
                        if driver == 'nfs':
                            driver_opts = {'share': workspace_model.volume.remote_path}
                        volume = Volume(vol_name, cont_path, task_workspace.mode, is_host=False, driver=driver,
                                        driver_opts=driver_opts)
                    workspace_volumes[task_workspace.name] = volume

            config.add_to_task(task_type, env_vars=env_vars, wksp_volumes=workspace_volumes)

        # Configure tasks for logging
        if settings.LOGGING_ADDRESS is not None:
            log_driver = DockerParameter('log-driver', 'syslog')
            # Must explicitly specify RFC3164 to ensure compatibility with logstash in Docker 1.11+
            syslog_format = DockerParameter('log-opt', 'syslog-format=rfc3164')
            log_address = DockerParameter('log-opt', 'syslog-address=%s' % settings.LOGGING_ADDRESS)
            if not job_exe.is_system:
                pre_task_tag = DockerParameter('log-opt', 'tag=%s' % config.get_task_id('pre'))
                config.add_to_task('pre', docker_params=[log_driver, syslog_format, log_address, pre_task_tag])
                post_task_tag = DockerParameter('log-opt', 'tag=%s' % config.get_task_id('post'))
                config.add_to_task('post', docker_params=[log_driver, syslog_format, log_address, post_task_tag])
                # TODO: remove es_urls parameter when Scale no longer supports old style job types
                es_urls = None
                # Use connection pool to get up-to-date list of elasticsearch nodes
                if settings.ELASTICSEARCH:
                    hosts = [host.host for host in settings.ELASTICSEARCH.transport.connection_pool.connections]
                    es_urls = ','.join(hosts)
                # Post task needs ElasticSearch URL to grab logs for old artifact registration
                es_param = DockerParameter('env', 'SCALE_ELASTICSEARCH_URLS=%s' % es_urls)
                config.add_to_task('post', docker_params=[es_param])
            main_task_tag = DockerParameter('log-opt', 'tag=%s' % config.get_task_id('main'))
            config.add_to_task('main', docker_params=[log_driver, syslog_format, log_address, main_task_tag])

    @staticmethod
    def _configure_main_task(config, job_exe, job_type, interface):
        """Configures the main task for the given execution with items specific to the main task

        :param config: The execution configuration
        :type config: :class:`job.configuration.json.execution.exe_config.ExecutionConfiguration`
        :param job_exe: The job execution model being scheduled
        :type job_exe: :class:`job.models.JobExecution`
        :param job_type: The job type model
        :type job_type: :class:`job.models.JobType`
        :param interface: The job interface
        :type interface: :class:`job.configuration.interface.job_interface.JobInterface`
        """

        # Set shared memory if required by this job type
        shared_mem = job_type.shared_mem_required
        if shared_mem > 0:
            shared_mem = int(math.ceil(shared_mem))
            env_vars = {'ALLOCATED_SHARED_MEM': shared_mem}
            config.add_to_task('main', docker_params=[DockerParameter('shm-size', '%dm' % shared_mem)],
                               env_vars=env_vars)

        job_config = job_type.get_job_configuration()
        mount_volumes = {}
        # TODO: use better interface method once we switch to Seed
        for mount in interface.get_dict()['mounts']:
            name = mount['name']
            mode = mount['mode']
            path = mount['path']
            volume_name = get_mount_volume_name(job_exe, name)
            volume = job_config.get_mount_volume(name, volume_name, path, mode)
            if volume:
                mount_volumes[name] = volume
            else:
                mount_volumes[name] = None
        config.add_to_task('main', mount_volumes=mount_volumes)

    @staticmethod
    def _configure_regular_job(config, job_exe):
        """Configures the given execution as a regular (non-system) job by adding pre and post tasks,
        input/output mounts, etc

        :param config: The execution configuration
        :type config: :class:`job.configuration.json.execution.exe_config.ExecutionConfiguration`
        :param job_exe: The job execution model being scheduled
        :type job_exe: :class:`job.models.JobExecution`
        """

        # TODO: configure main task command args
        config.create_tasks(['pull', 'pre', 'main', 'post'])
        config.add_to_task('pull', args=create_pull_command(job_exe.get_docker_image()))
        config.add_to_task('pre', args='scale_pre_steps -i %i' % job_exe.id)
        config.add_to_task('post', args='scale_post_steps -i %i' % job_exe.id)

        # Configure input workspaces
        ro_input_workspaces = {}
        rw_input_workspaces = {}
        for input_workspace in config.get_input_workspace_names():
            ro_input_workspaces[input_workspace] = TaskWorkspace(input_workspace, MODE_RO)
            rw_input_workspaces[input_workspace] = TaskWorkspace(input_workspace, MODE_RW)
        config.add_to_task('pre', workspaces=ro_input_workspaces)
        config.add_to_task('main', workspaces=ro_input_workspaces)
        # Post tasks have access to input workspaces in case input files need moved as part of parse results
        config.add_to_task('post', workspaces=rw_input_workspaces)

        # Configure output workspaces
        output_workspaces = {}
        for output_workspace in config.get_input_workspace_names():
            output_workspaces[output_workspace] = TaskWorkspace(output_workspace, MODE_RW)
        config.add_to_task('post', workspaces=output_workspaces)

        # Configure input/output mounts
        input_mnt_name = 'scale_input_mount'
        output_mnt_name = 'scale_output_mount'
        input_vol_name = get_job_exe_input_vol_name(job_exe)
        output_vol_name = get_job_exe_output_vol_name(job_exe)
        input_vol_ro = Volume(input_vol_name, SCALE_JOB_EXE_INPUT_PATH, MODE_RO, is_host=False)
        input_vol_rw = Volume(input_vol_name, SCALE_JOB_EXE_INPUT_PATH, MODE_RW, is_host=False)
        output_vol_ro = Volume(output_vol_name, SCALE_JOB_EXE_OUTPUT_PATH, MODE_RO, is_host=False)
        output_vol_rw = Volume(output_vol_name, SCALE_JOB_EXE_OUTPUT_PATH, MODE_RW, is_host=False)
        config.add_to_task('pre', mount_volumes={input_mnt_name: input_vol_rw, output_mnt_name: output_vol_rw})
        config.add_to_task('main', mount_volumes={input_mnt_name: input_vol_ro, output_mnt_name: output_vol_rw})
        config.add_to_task('post', mount_volumes={output_mnt_name: output_vol_ro})

        # Configure output directory
        # TODO: original output dir can be removed when Scale only supports Seed-based job types
        env_vars = {'job_output_dir': SCALE_JOB_EXE_OUTPUT_PATH, 'OUTPUT_DIR': SCALE_JOB_EXE_OUTPUT_PATH}
        config.add_to_task('main', env_vars=env_vars)

        # Configure task resources
        resources = job_exe.get_resources()
        # Pull-task and pre-task require full amount of resources
        config.add_to_task('pull', resources=resources)
        config.add_to_task('pre', resources=resources)
        # Main-task no longer requires the input file space
        resources.subtract(NodeResources([Disk(job_exe.input_file_size)]))
        config.add_to_task('main', resources=resources)
        # Post-task no longer requires any disk space
        resources.remove_resource('disk')
        config.add_to_task('post', resources=resources)

    def _configure_secrets(self, config, job_exe, job_type, interface):
        """Creates a copy of the configuration, configures secrets (masked in one of the copies), and applies any final
        configuration

        :param config: The execution configuration, where the secrets will be masked out
        :type config: :class:`job.configuration.json.execution.exe_config.ExecutionConfiguration`
        :param job_exe: The job execution model being scheduled
        :type job_exe: :class:`job.models.JobExecution`
        :param job_type: The job type model
        :type job_type: :class:`job.models.JobType`
        :param interface: The job interface
        :type interface: :class:`job.configuration.interface.job_interface.JobInterface`
        :returns: The copy of the execution configuration that contains the secrets
        :rtype: :class:`job.configuration.json.execution.exe_config.ExecutionConfiguration`
        """

        # Copy the configuration
        config_with_secrets = config.create_copy()

        # Configure settings values, some are secret
        if job_type.is_system:
            config.add_to_task('main', settings=self._system_settings_hidden)
            config_with_secrets.add_to_task('main', settings=self._system_settings)
        else:
            config.add_to_task('pre', settings=self._system_settings_hidden)
            config_with_secrets.add_to_task('pre', settings=self._system_settings)
            config.add_to_task('post', settings=self._system_settings_hidden)
            config_with_secrets.add_to_task('post', settings=self._system_settings)
            job_config = job_type.get_job_configuration()
            job_type_name = job_type.get_job_type_name()
            job_type_ver = job_type.get_job_type_version()
            job_index = '-'.join([job_type_name, job_type_ver]).replace('.', '_')
            secret_settings = secrets_mgr.retrieve_job_type_secrets(job_index)
            for _config, secrets_hidden in [(config, True), (config_with_secrets, False)]:
                task_settings = {}
                # TODO: use better interface method once we switch to Seed
                for setting in interface.get_dict()['settings']:
                    name = setting['name']
                    if setting['secret']:
                        value = secret_settings[name]
                        if value is not None and secrets_hidden:
                            value = '*****'
                    else:
                        value = job_config.get_setting_value(name)
                    task_settings[name] = value
                _config.add_to_task('main', settings=task_settings)

        # Configure env vars for settings
        for _config in [config, config_with_secrets]:
            for task_type in _config.get_task_types():
                env_vars = {}
                for name, value in _config.get_settings(task_type):
                    env_name = normalize_env_var_name(name)
                    env_vars[env_name] = value
                _config.add_to_task(task_type, env_vars=env_vars)

        # TODO: this feature should be removed once Scale drops support for old-style job types
        # Configure env vars defined in interface
        env_vars = interface.populate_env_vars_arguments(config, job_type, True)
        config.add_to_task('main', env_vars=env_vars)
        env_vars = interface.populate_env_vars_arguments(config_with_secrets, job_type, False)
        config_with_secrets.add_to_task('main', env_vars=env_vars)

        # Configure Docker parameters for env vars and Docker volumes
        for _config in [config, config_with_secrets]:
            existing_volumes = set()
            for task_type in _config.get_task_types():
                docker_params = []
                for name, value in _config.get_env_vars(task_type):
                    docker_params.append(DockerParameter('env', '%s=%s' % (name, value)))
                for name, volume in _config.get_volumes(task_type):
                    docker_params.append(volume.to_docker_param(is_created=(name in existing_volumes)))
                    existing_volumes.add(name)
                _config.add_to_task(task_type, docker_params=docker_params)

        # TODO: this feature should be removed once Scale drops support for job type docker params
        # Configure docker parameters listed in job type
        if job_type.docker_params:
            docker_params = []
            for key, value in job_type.docker_params:
                docker_params.append(DockerParameter(key, value))
            if docker_params:
                config.add_to_task('main', docker_params=docker_params)
                config_with_secrets.add_to_task('main', docker_params=docker_params)

        return config_with_secrets

    @staticmethod
    def _configure_system_job(config, job_exe):
        """Configures the given execution as a system job

        :param config: The execution configuration
        :type config: :class:`job.configuration.json.execution.exe_config.ExecutionConfiguration`
        :param job_exe: The job execution model being scheduled
        :type job_exe: :class:`job.models.JobExecution`
        """

        # TODO: configure main task command args
        config.add_to_task('main', resources=job_exe.get_resources())
