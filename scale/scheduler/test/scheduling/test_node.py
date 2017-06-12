from __future__ import unicode_literals

import django
from django.test import TestCase
from django.utils.timezone import now
from mock import MagicMock

import job.test.utils as job_test_utils
import queue.test.utils as queue_test_utils
from job.execution.job_exe import RunningJobExecution
from job.resources import NodeResources
from job.tasks.health_task import HealthTask
from job.tasks.pull_task import PullTask
from queue.job_exe import QueuedJobExecution
from scheduler.resources.agent import ResourceSet
from scheduler.resources.offer import ResourceOffer
from scheduler.scheduling.node import SchedulingNode


class TestSchedulingNode(TestCase):

    def setUp(self):
        django.setup()

    def test_accept_job_exe_next_task(self):
        """Tests successfully calling accept_job_exe_next_task()"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        offered_resources = NodeResources(cpus=10.0, mem=50.0)
        task_resources = NodeResources()
        watermark_resources = NodeResources(cpus=100.0, mem=500.0)
        resource_set = ResourceSet(offered_resources, task_resources, watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)

        job_exe_model = job_test_utils.create_job_exe()
        job_exe_model.cpus_scheduled = 1.0
        job_exe_model.mem_scheduled = 10.0
        job_exe_model.disk_in_scheduled = 0.0
        job_exe_model.disk_out_scheduled = 0.0
        job_exe_model.disk_total_scheduled = 0.0
        job_exe = RunningJobExecution(job_exe_model)
        waiting_tasks = []

        had_waiting_task = scheduling_node.accept_job_exe_next_task(job_exe, waiting_tasks)
        self.assertFalse(had_waiting_task)
        self.assertEqual(len(scheduling_node._allocated_running_job_exes), 1)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(NodeResources(cpus=1.0, mem=10.0)))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(NodeResources(cpus=9.0, mem=40.0)))
        self.assertListEqual(waiting_tasks, [])

    def test_accept_job_exe_next_task_no_jobs(self):
        """Tests calling accept_job_exe_next_task() when job exe tasks are not allowed"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = False
        offered_resources = NodeResources(cpus=10.0, mem=50.0)
        task_resources = NodeResources()
        watermark_resources = NodeResources(cpus=100.0, mem=500.0)
        resource_set = ResourceSet(offered_resources, task_resources, watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)

        job_exe_model = job_test_utils.create_job_exe()
        job_exe_model.cpus_scheduled = 1.0
        job_exe_model.mem_scheduled = 10.0
        job_exe_model.disk_in_scheduled = 0.0
        job_exe_model.disk_out_scheduled = 0.0
        job_exe_model.disk_total_scheduled = 0.0
        job_exe = RunningJobExecution(job_exe_model)
        waiting_tasks = []

        had_waiting_task = scheduling_node.accept_job_exe_next_task(job_exe, waiting_tasks)
        self.assertFalse(had_waiting_task)
        self.assertEqual(len(scheduling_node._allocated_running_job_exes), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(NodeResources()))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(NodeResources(cpus=10.0, mem=50.0)))
        self.assertListEqual(waiting_tasks, [])

    def test_accept_job_exe_next_task_canceled(self):
        """Tests calling accept_job_exe_next_task() when job exe gets canceled (no next task)"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        offered_resources = NodeResources(cpus=10.0, mem=50.0)
        task_resources = NodeResources()
        watermark_resources = NodeResources(cpus=100.0, mem=500.0)
        resource_set = ResourceSet(offered_resources, task_resources, watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)

        job_exe_model = job_test_utils.create_job_exe()
        job_exe_model.cpus_scheduled = 1.0
        job_exe_model.mem_scheduled = 10.0
        job_exe_model.disk_in_scheduled = 0.0
        job_exe_model.disk_out_scheduled = 0.0
        job_exe_model.disk_total_scheduled = 0.0
        job_exe = RunningJobExecution(job_exe_model)
        waiting_tasks = []

        job_exe.execution_canceled()
        had_waiting_task = scheduling_node.accept_job_exe_next_task(job_exe, waiting_tasks)
        self.assertFalse(had_waiting_task)
        self.assertEqual(len(scheduling_node._allocated_running_job_exes), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(NodeResources()))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(NodeResources(cpus=10.0, mem=50.0)))
        self.assertListEqual(waiting_tasks, [])

    def test_accept_job_exe_next_task_insufficient_resources(self):
        """Tests calling accept_job_exe_next_task() when there are not enough resources"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        offered_resources = NodeResources(cpus=10.0, mem=50.0)
        task_resources = NodeResources()
        watermark_resources = NodeResources(cpus=100.0, mem=500.0)
        resource_set = ResourceSet(offered_resources, task_resources, watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)

        job_exe_model = job_test_utils.create_job_exe()
        job_exe_model.cpus_scheduled = 11.0
        job_exe_model.mem_scheduled = 10.0
        job_exe_model.disk_in_scheduled = 0.0
        job_exe_model.disk_out_scheduled = 0.0
        job_exe_model.disk_total_scheduled = 0.0
        job_exe = RunningJobExecution(job_exe_model)
        waiting_tasks = []

        had_waiting_task = scheduling_node.accept_job_exe_next_task(job_exe, waiting_tasks)
        self.assertTrue(had_waiting_task)
        self.assertEqual(len(scheduling_node._allocated_running_job_exes), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(NodeResources()))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(NodeResources(cpus=10.0, mem=50.0)))
        self.assertListEqual(waiting_tasks, [job_exe.next_task()])

    def test_accept_new_job_exe(self):
        """Tests successfully calling accept_new_job_exe()"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        offered_resources = NodeResources(cpus=10.0, mem=50.0)
        task_resources = NodeResources()
        watermark_resources = NodeResources(cpus=100.0, mem=500.0)
        resource_set = ResourceSet(offered_resources, task_resources, watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)

        queue_model = queue_test_utils.create_queue(cpus_required=1.0, mem_required=10.0, disk_in_required=0.0,
                                                    disk_out_required=0.0, disk_total_required=0.0)
        job_exe = QueuedJobExecution(queue_model)

        accepted = scheduling_node.accept_new_job_exe(job_exe)
        self.assertTrue(accepted)
        self.assertEqual(len(scheduling_node._allocated_queued_job_exes), 1)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(NodeResources(cpus=1.0, mem=10.0)))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(NodeResources(cpus=9.0, mem=40.0)))
        self.assertEqual(job_exe.provided_node_id, node.id)

    def test_accept_new_job_exe_insufficient_resources(self):
        """Tests calling accept_new_job_exe() when there are not enough resources"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        offered_resources = NodeResources(cpus=10.0, mem=50.0)
        task_resources = NodeResources()
        watermark_resources = NodeResources(cpus=100.0, mem=500.0)
        resource_set = ResourceSet(offered_resources, task_resources, watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)

        queue_model = queue_test_utils.create_queue(cpus_required=11.0, mem_required=10.0, disk_in_required=0.0,
                                                    disk_out_required=0.0, disk_total_required=0.0)
        job_exe = QueuedJobExecution(queue_model)

        accepted = scheduling_node.accept_new_job_exe(job_exe)
        self.assertFalse(accepted)
        self.assertEqual(len(scheduling_node._allocated_queued_job_exes), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(NodeResources()))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(NodeResources(cpus=10.0, mem=50.0)))
        self.assertIsNone(job_exe.provided_node_id)

    def test_accept_new_job_exe_no_jobs(self):
        """Tests calling accept_new_job_exe() when new job exes are not allowed"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = False
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        offered_resources = NodeResources(cpus=10.0, mem=50.0)
        task_resources = NodeResources()
        watermark_resources = NodeResources(cpus=100.0, mem=500.0)
        resource_set = ResourceSet(offered_resources, task_resources, watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)

        queue_model = queue_test_utils.create_queue(cpus_required=1.0, mem_required=10.0, disk_in_required=0.0,
                                                    disk_out_required=0.0, disk_total_required=0.0)
        job_exe = QueuedJobExecution(queue_model)

        accepted = scheduling_node.accept_new_job_exe(job_exe)
        self.assertFalse(accepted)
        self.assertEqual(len(scheduling_node._allocated_queued_job_exes), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(NodeResources()))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(NodeResources(cpus=10.0, mem=50.0)))
        self.assertIsNone(job_exe.provided_node_id)

    def test_accept_node_tasks(self):
        """Tests successfully calling accept_node_tasks()"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        health_task = HealthTask('1234', 'agent_1')
        pull_task = PullTask('1234', 'agent_1')
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        node.get_next_tasks = MagicMock()
        node.get_next_tasks.return_value = [health_task, pull_task]
        node_task_resources = NodeResources()
        node_task_resources.add(health_task.get_resources())
        node_task_resources.add(pull_task.get_resources())
        offered_resources = NodeResources(cpus=100.0, mem=5000.0)
        expected_remaining_resources = NodeResources()
        expected_remaining_resources.add(offered_resources)
        expected_remaining_resources.subtract(node_task_resources)
        task_resources = NodeResources()
        watermark_resources = NodeResources(cpus=100.0, mem=5000.0)
        resource_set = ResourceSet(offered_resources, task_resources, watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)
        waiting_tasks = []

        had_waiting_task = scheduling_node.accept_node_tasks(now(), waiting_tasks)
        self.assertFalse(had_waiting_task)
        self.assertEqual(len(scheduling_node.allocated_tasks), 2)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(node_task_resources))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(expected_remaining_resources))
        self.assertListEqual(waiting_tasks, [])

    def test_accept_node_tasks_insufficient_resources(self):
        """Tests calling accept_node_tasks() when there are not enough resources"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        health_task = HealthTask('1234', 'agent_1')
        pull_task = PullTask('1234', 'agent_1')
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        node.get_next_tasks = MagicMock()
        node.get_next_tasks.return_value = [health_task, pull_task]
        offered_resources = NodeResources(cpus=0.0, mem=50.0)
        task_resources = NodeResources()
        watermark_resources = NodeResources(cpus=100.0, mem=500.0)
        resource_set = ResourceSet(offered_resources, task_resources, watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)
        waiting_tasks = []

        had_waiting_task = scheduling_node.accept_node_tasks(now(), waiting_tasks)
        self.assertTrue(had_waiting_task)
        self.assertEqual(len(scheduling_node.allocated_tasks), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(NodeResources()))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(offered_resources))
        self.assertListEqual(waiting_tasks, [health_task, pull_task])

    def test_add_allocated_offers(self):
        """Tests calling add_allocated_offers() when there are enough resources for everything"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        health_task = HealthTask('1234', 'agent_1')
        pull_task = PullTask('1234', 'agent_1')
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        node.get_next_tasks = MagicMock()
        node.get_next_tasks.return_value = [health_task, pull_task]
        offered_resources = NodeResources(cpus=100.0, mem=500.0)
        watermark_resources = NodeResources(cpus=100.0, mem=500.0)
        resource_set = ResourceSet(offered_resources, NodeResources(), watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)
        job_exe_model_1 = job_test_utils.create_job_exe()
        job_exe_model_1.cpus_scheduled = 1.0
        job_exe_model_1.mem_scheduled = 10.0
        job_exe_model_1.disk_in_scheduled = 0.0
        job_exe_model_1.disk_out_scheduled = 0.0
        job_exe_model_1.disk_total_scheduled = 0.0
        running_job_exe_1 = RunningJobExecution(job_exe_model_1)
        job_exe_model_2 = job_test_utils.create_job_exe()
        job_exe_model_2.cpus_scheduled = 2.0
        job_exe_model_2.mem_scheduled = 20.0
        job_exe_model_2.disk_in_scheduled = 0.0
        job_exe_model_2.disk_out_scheduled = 0.0
        job_exe_model_2.disk_total_scheduled = 0.0
        running_job_exe_2 = RunningJobExecution(job_exe_model_2)
        node_task_resources = NodeResources()
        node_task_resources.add(health_task.get_resources())
        node_task_resources.add(pull_task.get_resources())
        all_required_resources = NodeResources()
        all_required_resources.add(node_task_resources)
        all_required_resources.add(running_job_exe_1.next_task().get_resources())
        all_required_resources.add(running_job_exe_2.next_task().get_resources())
        expected_remaining_resources = NodeResources()
        expected_remaining_resources.add(offered_resources)
        expected_remaining_resources.subtract(all_required_resources)

        # Set up node with node tasks and job exes (there would never be queued job exes since they would be scheduled
        # before add_allocated_offers() was called
        scheduling_node.accept_node_tasks(now(), [])
        scheduling_node.accept_job_exe_next_task(running_job_exe_1, [])
        scheduling_node.accept_job_exe_next_task(running_job_exe_2, [])
        self.assertEqual(len(scheduling_node.allocated_tasks), 2)
        self.assertEqual(len(scheduling_node._allocated_running_job_exes), 2)
        self.assertEqual(len(scheduling_node._allocated_queued_job_exes), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(all_required_resources))

        # Set up offers (we get back more than we need)
        offer_1 = ResourceOffer('offer_1', 'agent_1', '1234', NodeResources(cpus=1.0), now())
        offer_2 = ResourceOffer('offer_2', 'agent_1', '1234', all_required_resources, now())
        offer_3 = ResourceOffer('offer_3', 'agent_1', '1234', NodeResources(cpus=7.5, mem=600.0, disk=800.0), now())

        scheduling_node.add_allocated_offers([offer_1, offer_2, offer_3])
        self.assertListEqual(scheduling_node.allocated_offers, [offer_1, offer_2, offer_3])
        # All allocated tasks and job exes should still be here
        self.assertEqual(len(scheduling_node.allocated_tasks), 2)
        self.assertEqual(len(scheduling_node._allocated_running_job_exes), 2)
        self.assertEqual(len(scheduling_node._allocated_queued_job_exes), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(all_required_resources))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(expected_remaining_resources))

    def test_add_allocated_offers_remove_job_exes(self):
        """Tests calling add_allocated_offers() when there are not enough resources for the job exes"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        health_task = HealthTask('1234', 'agent_1')
        pull_task = PullTask('1234', 'agent_1')
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        node.get_next_tasks = MagicMock()
        node.get_next_tasks.return_value = [health_task, pull_task]
        offered_resources = NodeResources(cpus=100.0, mem=500.0)
        watermark_resources = NodeResources(cpus=100.0, mem=500.0)
        resource_set = ResourceSet(offered_resources, NodeResources(), watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)
        job_exe_model_1 = job_test_utils.create_job_exe()
        job_exe_model_1.cpus_scheduled = 1.0
        job_exe_model_1.mem_scheduled = 10.0
        job_exe_model_1.disk_in_scheduled = 0.0
        job_exe_model_1.disk_out_scheduled = 0.0
        job_exe_model_1.disk_total_scheduled = 0.0
        running_job_exe_1 = RunningJobExecution(job_exe_model_1)
        job_exe_model_2 = job_test_utils.create_job_exe()
        job_exe_model_2.cpus_scheduled = 2.0
        job_exe_model_2.mem_scheduled = 20.0
        job_exe_model_2.disk_in_scheduled = 0.0
        job_exe_model_2.disk_out_scheduled = 0.0
        job_exe_model_2.disk_total_scheduled = 0.0
        running_job_exe_2 = RunningJobExecution(job_exe_model_2)
        node_task_resources = NodeResources()
        node_task_resources.add(health_task.get_resources())
        node_task_resources.add(pull_task.get_resources())
        all_required_resources = NodeResources()
        all_required_resources.add(node_task_resources)
        all_required_resources.add(running_job_exe_1.next_task().get_resources())
        all_required_resources.add(running_job_exe_2.next_task().get_resources())
        expected_remaining_resources = NodeResources()
        expected_remaining_resources.add(offered_resources)
        expected_remaining_resources.subtract(node_task_resources)

        # Set up node with node tasks and job exes (there would never be queued job exes since they would be scheduled
        # before add_allocated_offers() was called
        scheduling_node.accept_node_tasks(now(), [])
        scheduling_node.accept_job_exe_next_task(running_job_exe_1, [])
        scheduling_node.accept_job_exe_next_task(running_job_exe_2, [])
        self.assertEqual(len(scheduling_node.allocated_tasks), 2)
        self.assertEqual(len(scheduling_node._allocated_running_job_exes), 2)
        self.assertEqual(len(scheduling_node._allocated_queued_job_exes), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(all_required_resources))

        # Set up offers (enough for node tasks but not enough for job exes)
        offer_1 = ResourceOffer('offer_1', 'agent_1', '1234', NodeResources(cpus=0.5), now())
        offer_2 = ResourceOffer('offer_2', 'agent_1', '1234', node_task_resources, now())

        scheduling_node.add_allocated_offers([offer_1, offer_2])
        self.assertListEqual(scheduling_node.allocated_offers, [offer_1, offer_2])
        # All allocated tasks should still be here, but not job exes
        self.assertEqual(len(scheduling_node.allocated_tasks), 2)
        self.assertEqual(len(scheduling_node._allocated_running_job_exes), 0)
        self.assertEqual(len(scheduling_node._allocated_queued_job_exes), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(node_task_resources))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(expected_remaining_resources))

    def test_add_allocated_offers_remove_all_tasks(self):
        """Tests calling add_allocated_offers() when there are not enough resources for the job exes or node tasks"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        health_task = HealthTask('1234', 'agent_1')
        pull_task = PullTask('1234', 'agent_1')
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        node.get_next_tasks = MagicMock()
        node.get_next_tasks.return_value = [health_task, pull_task]
        offered_resources = NodeResources(cpus=100.0, mem=500.0)
        watermark_resources = NodeResources(cpus=100.0, mem=500.0)
        resource_set = ResourceSet(offered_resources, NodeResources(), watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)
        job_exe_model_1 = job_test_utils.create_job_exe()
        job_exe_model_1.cpus_scheduled = 1.0
        job_exe_model_1.mem_scheduled = 10.0
        job_exe_model_1.disk_in_scheduled = 0.0
        job_exe_model_1.disk_out_scheduled = 0.0
        job_exe_model_1.disk_total_scheduled = 0.0
        running_job_exe_1 = RunningJobExecution(job_exe_model_1)
        job_exe_model_2 = job_test_utils.create_job_exe()
        job_exe_model_2.cpus_scheduled = 2.0
        job_exe_model_2.mem_scheduled = 20.0
        job_exe_model_2.disk_in_scheduled = 0.0
        job_exe_model_2.disk_out_scheduled = 0.0
        job_exe_model_2.disk_total_scheduled = 0.0
        running_job_exe_2 = RunningJobExecution(job_exe_model_2)
        node_task_resources = NodeResources()
        node_task_resources.add(health_task.get_resources())
        node_task_resources.add(pull_task.get_resources())
        all_required_resources = NodeResources()
        all_required_resources.add(node_task_resources)
        all_required_resources.add(running_job_exe_1.next_task().get_resources())
        all_required_resources.add(running_job_exe_2.next_task().get_resources())
        expected_remaining_resources = NodeResources()
        expected_remaining_resources.add(offered_resources)
        expected_remaining_resources.subtract(node_task_resources)

        # Set up node with node tasks and job exes (there would never be queued job exes since they would be scheduled
        # before add_allocated_offers() was called
        scheduling_node.accept_node_tasks(now(), [])
        scheduling_node.accept_job_exe_next_task(running_job_exe_1, [])
        scheduling_node.accept_job_exe_next_task(running_job_exe_2, [])
        self.assertEqual(len(scheduling_node.allocated_tasks), 2)
        self.assertEqual(len(scheduling_node._allocated_running_job_exes), 2)
        self.assertEqual(len(scheduling_node._allocated_queued_job_exes), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(all_required_resources))

        # Set up offers (not enough for job exes or node tasks)
        offer_1 = ResourceOffer('offer_1', 'agent_1', '1234', NodeResources(cpus=0.1, mem=600.0), now())

        scheduling_node.add_allocated_offers([offer_1])
        self.assertListEqual(scheduling_node.allocated_offers, [offer_1])
        # All allocated tasks and job exes should be gone
        self.assertEqual(len(scheduling_node.allocated_tasks), 0)
        self.assertEqual(len(scheduling_node._allocated_running_job_exes), 0)
        self.assertEqual(len(scheduling_node._allocated_queued_job_exes), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(NodeResources()))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(offered_resources))

    def test_reset_new_job_exes(self):
        """Tests calling reset_new_job_exes() successfully"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        offered_resources = NodeResources(cpus=100.0, mem=500.0)
        watermark_resources = NodeResources(cpus=100.0, mem=500.0)
        resource_set = ResourceSet(offered_resources, NodeResources(), watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)
        queue_model_1 = queue_test_utils.create_queue(cpus_required=2.0, mem_required=60.0, disk_in_required=0.0,
                                                      disk_out_required=0.0, disk_total_required=0.0)
        job_exe_1 = QueuedJobExecution(queue_model_1)
        queue_model_2 = queue_test_utils.create_queue(cpus_required=4.5, mem_required=400.0, disk_in_required=0.0,
                                                      disk_out_required=0.0, disk_total_required=0.0)
        job_exe_2 = QueuedJobExecution(queue_model_2)
        allocated_resources = NodeResources()
        allocated_resources.add(job_exe_1.required_resources)
        allocated_resources.add(job_exe_2.required_resources)

        # Set up node with queued job exes
        scheduling_node.accept_new_job_exe(job_exe_1)
        scheduling_node.accept_new_job_exe(job_exe_2)
        self.assertEqual(len(scheduling_node._allocated_queued_job_exes), 2)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(allocated_resources))

        # Reset queued job exes and check that everything is back to square one
        scheduling_node.reset_new_job_exes()
        self.assertEqual(len(scheduling_node._allocated_queued_job_exes), 0)
        self.assertTrue(scheduling_node.allocated_resources.is_equal(NodeResources()))
        self.assertTrue(scheduling_node._remaining_resources.is_equal(offered_resources))

    def test_score_job_exe_for_reservation(self):
        """Tests calling score_job_exe_for_reservation() successfully"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        offered_resources = NodeResources(cpus=20.0, mem=100.0)
        watermark_resources = NodeResources(cpus=200.0, mem=700.0)
        resource_set = ResourceSet(offered_resources, NodeResources(), watermark_resources)
        task = HealthTask('1234', 'agent_1')  # Resources are 0.1 CPUs and 32 MiB memory
        job_exe_model_1 = job_test_utils.create_job_exe()
        job_exe_model_1.job.priority = 1000
        job_exe_model_1.cpus_scheduled = 10.0
        job_exe_model_1.mem_scheduled = 50.0
        job_exe_model_1.disk_in_scheduled = 0.0
        job_exe_model_1.disk_out_scheduled = 0.0
        job_exe_model_1.disk_total_scheduled = 0.0
        job_exe_1 = RunningJobExecution(job_exe_model_1)
        job_exe_model_2 = job_test_utils.create_job_exe()
        job_exe_model_2.job.priority = 100
        job_exe_model_2.cpus_scheduled = 56.0
        job_exe_model_2.mem_scheduled = 15.0
        job_exe_model_2.disk_in_scheduled = 0.0
        job_exe_model_2.disk_out_scheduled = 0.0
        job_exe_model_2.disk_total_scheduled = 0.0
        job_exe_2 = RunningJobExecution(job_exe_model_2)
        scheduling_node = SchedulingNode('agent_1', node, [task], [job_exe_1, job_exe_2], resource_set)
        queue_model_1 = queue_test_utils.create_queue(priority=100, cpus_required=8.0, mem_required=40.0,
                                                      disk_in_required=0.0, disk_out_required=0.0,
                                                      disk_total_required=0.0)
        job_exe_1 = QueuedJobExecution(queue_model_1)
        queue_model_2 = queue_test_utils.create_queue(priority=1000, cpus_required=8.0, mem_required=40.0,
                                                      disk_in_required=0.0, disk_out_required=0.0,
                                                      disk_total_required=0.0)
        job_exe_2 = QueuedJobExecution(queue_model_2)
        scheduling_node.accept_new_job_exe(job_exe_1)
        scheduling_node.accept_new_job_exe(job_exe_2)

        # We are going to try to reserve the node for a job execution with priority 120
        # Calculate available resources for reservation:
        # Watermark (200, 700) - System Tasks (0.1, 32) - Higher Priority Existing Job Exes (56, 15) -  Higher Priority
        # New Job Exes (8, 40) = 135.9 CPUs, 613 memory
        # This new job should fit for reservation
        queue_model = queue_test_utils.create_queue(priority=120, cpus_required=130.0, mem_required=600.0,
                                                    disk_in_required=0.0, disk_out_required=0.0,
                                                    disk_total_required=0.0)
        job_exe = QueuedJobExecution(queue_model)
        # Expected available 5.9 CPUs and 13 MiB memory "left" on node
        # (available above - new job we are scoring)
        # First 2 job types should fit, next 2 are too big, so score should be 2
        job_type_resource_1 = NodeResources(cpus=2.0, mem=10.0)
        job_type_resource_2 = NodeResources(cpus=5.5, mem=12.0)
        job_type_resource_3 = NodeResources(cpus=6.0, mem=10.0)
        job_type_resource_4 = NodeResources(cpus=2.0, mem=14.0)

        score = scheduling_node.score_job_exe_for_reservation(job_exe, [job_type_resource_1, job_type_resource_2,
                                                                        job_type_resource_3, job_type_resource_4])
        self.assertEqual(score, 2)

    def test_score_job_exe_for_reservation_insufficient_resources(self):
        """Tests calling score_job_exe_for_reservation() when there are not enough resources to reserve for the job"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        offered_resources = NodeResources(cpus=20.0, mem=100.0)
        watermark_resources = NodeResources(cpus=200.0, mem=700.0)
        resource_set = ResourceSet(offered_resources, NodeResources(), watermark_resources)
        task = HealthTask('1234', 'agent_1')  # Resources are 0.1 CPUs and 32 MiB memory
        job_exe_model_1 = job_test_utils.create_job_exe()
        job_exe_model_1.job.priority = 1000
        job_exe_model_1.cpus_scheduled = 10.0
        job_exe_model_1.mem_scheduled = 50.0
        job_exe_model_1.disk_in_scheduled = 0.0
        job_exe_model_1.disk_out_scheduled = 0.0
        job_exe_model_1.disk_total_scheduled = 0.0
        job_exe_1 = RunningJobExecution(job_exe_model_1)
        job_exe_model_2 = job_test_utils.create_job_exe()
        job_exe_model_2.job.priority = 100
        job_exe_model_2.cpus_scheduled = 56.0
        job_exe_model_2.mem_scheduled = 15.0
        job_exe_model_2.disk_in_scheduled = 0.0
        job_exe_model_2.disk_out_scheduled = 0.0
        job_exe_model_2.disk_total_scheduled = 0.0
        job_exe_2 = RunningJobExecution(job_exe_model_2)
        scheduling_node = SchedulingNode('agent_1', node, [task], [job_exe_1, job_exe_2], resource_set)
        queue_model_1 = queue_test_utils.create_queue(priority=100, cpus_required=8.0, mem_required=40.0,
                                                      disk_in_required=0.0, disk_out_required=0.0,
                                                      disk_total_required=0.0)
        job_exe_1 = QueuedJobExecution(queue_model_1)
        queue_model_2 = queue_test_utils.create_queue(priority=1000, cpus_required=8.0, mem_required=40.0,
                                                      disk_in_required=0.0, disk_out_required=0.0,
                                                      disk_total_required=0.0)
        job_exe_2 = QueuedJobExecution(queue_model_2)
        scheduling_node.accept_new_job_exe(job_exe_1)
        scheduling_node.accept_new_job_exe(job_exe_2)

        # We are going to try to reserve the node for a job execution with priority 120
        # Calculate available resources for reservation:
        # Watermark (200, 700) - System Tasks (0.1, 32) - Higher Priority Existing Job Exes (56, 15) -  Higher Priority
        # New Job Exes (8, 40) = 135.9 CPUs, 613 memory
        # This new job should NOT fit for reservation
        queue_model = queue_test_utils.create_queue(priority=120, cpus_required=140.0, mem_required=600.0,
                                                    disk_in_required=0.0, disk_out_required=0.0,
                                                    disk_total_required=0.0)
        job_exe = QueuedJobExecution(queue_model)
        job_type_resource_1 = NodeResources(cpus=2.0, mem=10.0)

        score = scheduling_node.score_job_exe_for_reservation(job_exe, [job_type_resource_1])
        self.assertIsNone(score)

    def test_score_job_exe_for_scheduling(self):
        """Tests calling score_job_exe_for_scheduling() successfully"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        offered_resources = NodeResources(cpus=20.0, mem=100.0)
        task_resources = NodeResources(cpus=100.0, mem=500.0)
        watermark_resources = NodeResources(cpus=200.0, mem=700.0)
        resource_set = ResourceSet(offered_resources, task_resources, watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)
        # Allocate 10 CPUs and 50 MiB memory to existing job execution
        job_exe_model = job_test_utils.create_job_exe()
        job_exe_model.cpus_scheduled = 10.0
        job_exe_model.mem_scheduled = 50.0
        job_exe_model.disk_in_scheduled = 0.0
        job_exe_model.disk_out_scheduled = 0.0
        job_exe_model.disk_total_scheduled = 0.0
        job_exe = RunningJobExecution(job_exe_model)
        scheduling_node.accept_job_exe_next_task(job_exe, [])

        # Should have 10 CPUs and 50 MiB memory left, so this should be scheduled
        queue_model = queue_test_utils.create_queue(cpus_required=5.0, mem_required=40.0, disk_in_required=0.0,
                                                    disk_out_required=0.0, disk_total_required=0.0)
        job_exe = QueuedJobExecution(queue_model)
        # Expected available 85 CPUs and 110 MiB memory "left" on node
        # (watermark - current tasks - allocated - new job we are scoring)
        # First 2 job types should fit, next 2 are too big, so score should be 2
        job_type_resource_1 = NodeResources(cpus=2.0, mem=10.0)
        job_type_resource_2 = NodeResources(cpus=85.0, mem=109.0)
        job_type_resource_3 = NodeResources(cpus=86.0, mem=10.0)
        job_type_resource_4 = NodeResources(cpus=2.0, mem=111.0)

        score = scheduling_node.score_job_exe_for_scheduling(job_exe, [job_type_resource_1, job_type_resource_2,
                                                                       job_type_resource_3, job_type_resource_4])
        self.assertEqual(score, 2)

    def test_score_job_exe_for_scheduling_insufficient_resources(self):
        """Tests calling score_job_exe_for_scheduling() when there are not enough resources to schedule the job"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        offered_resources = NodeResources(cpus=20.0, mem=100.0)
        task_resources = NodeResources(cpus=100.0, mem=500.0)
        watermark_resources = NodeResources(cpus=200.0, mem=700.0)
        resource_set = ResourceSet(offered_resources, task_resources, watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)
        # Allocate 10 CPUs and 50 MiB memory to existing job execution
        job_exe_model = job_test_utils.create_job_exe()
        job_exe_model.cpus_scheduled = 10.0
        job_exe_model.mem_scheduled = 50.0
        job_exe_model.disk_in_scheduled = 0.0
        job_exe_model.disk_out_scheduled = 0.0
        job_exe_model.disk_total_scheduled = 0.0
        job_exe = RunningJobExecution(job_exe_model)
        scheduling_node.accept_job_exe_next_task(job_exe, [])

        # Should have 10 CPUs and 50 MiB memory left, so this job execution is too big
        queue_model = queue_test_utils.create_queue(cpus_required=15.0, mem_required=40.0, disk_in_required=0.0,
                                                    disk_out_required=0.0, disk_total_required=0.0)
        job_exe = QueuedJobExecution(queue_model)

        score = scheduling_node.score_job_exe_for_scheduling(job_exe, [])
        self.assertIsNone(score)

    def test_start_job_exe_tasks(self):
        """Tests calling start_job_exe_tasks() successfully"""

        node = MagicMock()
        node.hostname = 'host_1'
        node.id = 1
        node.is_ready_for_new_job = MagicMock()
        node.is_ready_for_new_job.return_value = True
        node.is_ready_for_next_job_task = MagicMock()
        node.is_ready_for_next_job_task.return_value = True
        offered_resources = NodeResources(cpus=20.0, mem=100.0)
        watermark_resources = NodeResources(cpus=200.0, mem=700.0)
        resource_set = ResourceSet(offered_resources, NodeResources(), watermark_resources)
        scheduling_node = SchedulingNode('agent_1', node, [], [], resource_set)
        job_exe_model_1 = job_test_utils.create_job_exe()
        job_exe_model_1.cpus_scheduled = 10.0
        job_exe_model_1.mem_scheduled = 50.0
        job_exe_model_1.disk_in_scheduled = 0.0
        job_exe_model_1.disk_out_scheduled = 0.0
        job_exe_model_1.disk_total_scheduled = 0.0
        job_exe_1 = RunningJobExecution(job_exe_model_1)
        job_exe_model_2 = job_test_utils.create_job_exe()
        job_exe_model_2.cpus_scheduled = 5.0
        job_exe_model_2.mem_scheduled = 25.0
        job_exe_model_2.disk_in_scheduled = 0.0
        job_exe_model_2.disk_out_scheduled = 0.0
        job_exe_model_2.disk_total_scheduled = 0.0
        job_exe_2 = RunningJobExecution(job_exe_model_2)
        scheduling_node.accept_job_exe_next_task(job_exe_1, [])
        scheduling_node.accept_job_exe_next_task(job_exe_2, [])
        self.assertEqual(len(scheduling_node._allocated_running_job_exes), 2)

        job_exe_1.execution_canceled()  # Execution canceled, so it will not have a next task to start

        scheduling_node.start_job_exe_tasks()
        self.assertEqual(len(scheduling_node._allocated_running_job_exes), 0)
        self.assertEqual(len(scheduling_node.allocated_tasks), 1)  # Only job_exe_2 had a next task
