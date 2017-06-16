# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-06-16 14:52
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('queue', '0010_auto_20170615_1704'),
    ]

    def populate_queue_resources(apps, schema_editor):
        from node.resources.node_resources import NodeResources
        from node.resources.resource import Cpus, Disk, Mem

        # Go through all of the queue models and populate their new resources columns
        Queue = apps.get_model('queue', 'Queue')
        total_count = Queue.objects.all().count()
        print 'Populating new resources field for %s queue models' % str(total_count)
        done_count = 0
        batch_size = 1000
        while done_count < total_count:
            percent = (float(done_count) / float(total_count)) * 100.00
            print 'Completed %s of %s queue models (%f%%)' % (done_count, total_count, percent)
            batch_end = done_count + batch_size
            for queue in Queue.objects.order_by('job_exe_id')[done_count:batch_end]:
                cpus = queue.cpus_required
                mem = queue.mem_required
                disk = queue.disk_total_required
                resources = NodeResources([Cpus(cpus), Mem(mem), Disk(disk)])
                queue.resources = resources.get_json().get_dict()
                queue.save()
            done_count += batch_size
        print 'All %s queue models completed' % str(total_count)

    operations = [
        migrations.RunPython(populate_queue_resources),
    ]
