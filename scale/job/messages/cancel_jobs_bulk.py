"""Defines a command message that performs a bulk cancel operation"""
from __future__ import unicode_literals

import logging

from django.utils.timezone import now

from job.messages.cancel_jobs import create_cancel_jobs_messages
from job.models import Job
from messaging.messages.message import CommandMessage
from util.parse import datetime_to_string, parse_datetime

# How many jobs to handle in a single execution of this message
MAX_BATCH_SIZE = 1000


logger = logging.getLogger(__name__)


def create_cancel_jobs_bulk_message(started=None, ended=None, error_categories=None, error_ids=None, job_ids=None,
                                    job_type_ids=None, status=None):
    """Creates a message to perform a bulk job cancel operation. The parameters are applied as filters to the jobs
    affected by the cancel.

    :param started: The start time of the jobs
    :type started: :class:`datetime.datetime`
    :param ended: The end time of the jobs
    :type ended: :class:`datetime.datetime`
    :param error_categories: A list of error categories
    :type error_categories: list
    :param error_ids: A list of error IDs
    :type error_ids: list
    :param job_ids: A list of job IDs
    :type job_ids: list
    :param job_type_ids: A list of job type IDs
    :type job_type_ids: list
    :param status: The job status
    :type status: str
    :return: The message
    :rtype: :class:`job.messages.cancel_jobs_bulk.CancelJobsBulk`
    """

    message = CancelJobsBulk()
    message.started = started
    message.ended = ended
    message.error_categories = error_categories
    message.error_ids = error_ids
    message.job_ids = job_ids
    message.job_type_ids = job_type_ids
    message.status = status

    return message


class CancelJobsBulk(CommandMessage):
    """Command message that performs a bulk cancel operation
    """

    def __init__(self):
        """Constructor
        """

        super(CancelJobsBulk, self).__init__('cancel_jobs_bulk')

        self.current_job_id = None  # Keeps track of where the bulk operation is
        self.started = None
        self.ended = None
        self.error_categories = None
        self.error_ids = None
        self.job_ids = None
        self.job_type_ids = None
        self.status = None

    def to_json(self):
        """See :meth:`messaging.messages.message.CommandMessage.to_json`
        """

        json_dict = {}
        if self.current_job_id is not None:
            json_dict['current_job_id'] = self.current_job_id
        if self.started is not None:
            json_dict['started'] = datetime_to_string(self.started)
        if self.ended is not None:
            json_dict['ended'] = datetime_to_string(self.ended)
        if self.error_categories is not None:
            json_dict['error_categories'] = self.error_categories
        if self.error_ids is not None:
            json_dict['error_ids'] = self.error_ids
        if self.job_ids is not None:
            json_dict['job_ids'] = self.job_ids
        if self.job_type_ids is not None:
            json_dict['job_type_ids'] = self.job_type_ids
        if self.status is not None:
            json_dict['status'] = self.status

        return json_dict

    @staticmethod
    def from_json(json_dict):
        """See :meth:`messaging.messages.message.CommandMessage.from_json`
        """

        message = CancelJobsBulk()
        if 'current_job_id' in json_dict:
            message.current_job_id = json_dict['current_job_id']
        if 'started' in json_dict:
            message.started = parse_datetime(json_dict['started'])
        if 'ended' in json_dict:
            message.ended = parse_datetime(json_dict['ended'])
        if 'error_categories' in json_dict:
            message.error_categories = json_dict['error_categories']
        if 'error_ids' in json_dict:
            message.error_ids = json_dict['error_ids']
        if 'job_ids' in json_dict:
            message.job_ids = json_dict['job_ids']
        if 'job_type_ids' in json_dict:
            message.job_type_ids = json_dict['job_type_ids']
        if 'status' in json_dict:
            message.status = json_dict['status']

        return message

    def execute(self):
        """See :meth:`messaging.messages.message.CommandMessage.execute`
        """

        # Retrieve jobs that match filter criteria up to the max batch size
        # Jobs are retrieved in descending order by ID, with the current_job_id field decreasing with each batch so that
        # each subsequent CancelJobsBulk message advances through the jobs
        statuses = [self.status] if self.status else None
        job_qry = Job.objects.filter_jobs(started=self.started, ended=self.ended, statuses=statuses,
                                          job_ids=self.job_ids, job_type_ids=self.job_type_ids,
                                          error_categories=self.error_categories, error_ids=self.error_ids,
                                          order=['-id'])
        if self.current_job_id:
            job_qry = job_qry.filter(id__lt=self.current_job_id)

        cancel_job_ids = []
        batch_count = 0
        last_job_id = None
        for job in job_qry.defer('output')[:MAX_BATCH_SIZE]:
            batch_count += 1
            last_job_id = job.id
            if job.can_be_canceled():
                cancel_job_ids.append(job.id)
        cancel_count = len(cancel_job_ids)

        if batch_count == MAX_BATCH_SIZE:
            # Hit max size, need to create new bulk message identical to this one but with decreased current_job_id
            # field so the next message does the next batch worth of jobs
            logger.info('Reached max size of %d jobs, creating new message for next %d jobs', MAX_BATCH_SIZE,
                        MAX_BATCH_SIZE)
            msg = CancelJobsBulk.from_json(self.to_json())
            msg.current_job_id = last_job_id
            self.new_messages.append(msg)

        if cancel_count > 0:
            logger.info('Found %d job(s) to cancel, creating messages', cancel_count)
            self.new_messages.extend(create_cancel_jobs_messages(cancel_job_ids, now()))
        else:
            logger.info('Found no jobs to cancel')

        return True
