"""Defines the class for a cleanup task"""
from __future__ import unicode_literals

import datetime

from job.tasks.base_task import AtomicCounter
from job.tasks.node_task import NodeTask
from node.resources.node_resources import NodeResources
from node.resources.resource import Cpus, Mem


CLEANUP_TASK_ID_PREFIX = 'scale_cleanup'
COUNTER = AtomicCounter()


class CleanupTask(NodeTask):
    """Represents a task that cleans up after job executions. This class is thread-safe.
    """

    def __init__(self, framework_id, agent_id, job_exes):
        """Constructor

        :param framework_id: The framework ID
        :type framework_id: string
        :param agent_id: The agent ID
        :type agent_id: string
        :param job_exes: The list of job executions to clean up
        :type job_exes: [:class:`job.execution.job_exe.RunningJobExecution`]
        """

        task_id = '%s_%s_%d' % (CLEANUP_TASK_ID_PREFIX, framework_id, COUNTER.get_next())
        super(CleanupTask, self).__init__(task_id, 'Scale Cleanup', agent_id)

        self._job_exes = job_exes
        self._is_initial_cleanup = not self._job_exes  # This is an initial clean up if job_exes is empty

        self._uses_docker = False
        self._docker_image = None
        self._docker_params = []
        self._is_docker_privileged = False
        self._running_timeout_threshold = datetime.timedelta(minutes=10)

        # Define basic command pieces
        if_cmd = 'if %s ; then %s ; else %s ; fi'
        for_cmd = 'for %s in `%s`; do %s; done'
        all_containers_cmd = 'docker ps -a --format \'{{.Names}}\''
        nonrunning_filters = '-f status=created -f status=dead -f status=exited'
        all_nonrunning_containers_cmd = 'docker ps %s --format \'{{.Names}}\'' % nonrunning_filters
        all_volumes_cmd = 'docker volume ls -q'
        all_scale_dangling_volumes_cmd = 'docker volume ls -f dangling=true -q | grep scale_'
        container_delete_cmd = 'docker rm $cont'
        volume_delete_cmd = 'docker volume rm $vol'
        is_scale_container = 'docker inspect $cont | grep -q %s' % framework_id

        # Create commands that list the containers/volumes to delete
        if self._is_initial_cleanup:
            # Initial clean up deletes all non-running containers
            container_list_cmd = all_nonrunning_containers_cmd

            # TODO: once we upgrade to a later version of Docker (1.12+), we can delete volumes based on their name
            # (without grep) starting with "scale_" (and also dangling)
            # Initial clean up deletes all dangling Docker volumes named with "scale_" prefix
            volume_list_cmd = all_scale_dangling_volumes_cmd

            #We do not need to delete any stuck containers on initial cleanup
            delete_stuck_container_cmd = ':'
        else:
            # Deletes all containers and volumes for the given job executions
            containers = []
            volumes = []
            for job_exe in self._job_exes:
                containers.extend(job_exe.get_container_names())
                volumes.extend(job_exe.docker_volumes)
            # Container/volume lists are generated by greping entire list from Docker against the specific
            # containers/volumes we are looking for
            container_list_cmd = '%s | grep -e %s' % (all_containers_cmd, ' -e '.join(containers))
            volume_list_cmd = '%s | grep -e %s' % (all_volumes_cmd, ' -e '.join(volumes))

            #Delete containers that are stuck so that volumes can be cleaned up properly
            delete_stuck_container_cmd = for_cmd % ('cont',
                                                    all_nonrunning_containers_cmd,
                                                    if_cmd % (is_scale_container, container_delete_cmd, ':'))


        delete_containers_cmd = for_cmd % ('cont', container_list_cmd, container_delete_cmd)
        delete_volumes_cmd = for_cmd % ('vol', volume_list_cmd, volume_delete_cmd)

        # Create overall command that deletes containers and volumes for the job executions
        self._command = '%s; %s; %s' % (delete_containers_cmd, delete_stuck_container_cmd, delete_volumes_cmd)

        # Node task properties
        self.task_type = 'cleanup'
        self.title = 'Node Cleanup'
        self.description = 'Performs Docker container and volume cleanup on the node'

    @property
    def is_initial_cleanup(self):
        """Indicates whether this is an initial clean up job (True) or not (False)

        :returns: Whether this is an initial clean up job
        :rtype: bool
        """

        return self._is_initial_cleanup

    @property
    def job_exes(self):
        """Returns the list of job executions to clean up

        :returns: The list of job executions to clean up
        :rtype: [:class:`job.execution.job_exe.RunningJobExecution`]
        """

        return self._job_exes

    def get_resources(self):
        """See :meth:`job.tasks.base_task.Task.get_resources`
        """

        return NodeResources([Cpus(0.1), Mem(32.0)])
