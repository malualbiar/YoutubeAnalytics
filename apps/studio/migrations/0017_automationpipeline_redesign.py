from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('studio', '0016_automationpipeline'),
    ]

    operations = [
        # Drop old fields
        migrations.RemoveField(model_name='automationpipeline', name='steps_config'),
        migrations.RemoveField(model_name='automationpipeline', name='current_step_index'),
        migrations.RemoveField(model_name='automationpipeline', name='result_download_job_id'),
        migrations.RemoveField(model_name='automationpipeline', name='result_lyric_project_id'),
        migrations.RemoveField(model_name='automationpipeline', name='result_publishing_job_id'),
        # Add new fields
        migrations.AddField(
            model_name='automationpipeline',
            name='youtube_urls',
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name='automationpipeline',
            name='shared_config',
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name='automationpipeline',
            name='results',
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name='automationpipeline',
            name='current_song_index',
            field=models.IntegerField(default=0),
        ),
        # Update status choices (remove PAUSED)
        migrations.AlterField(
            model_name='automationpipeline',
            name='status',
            field=models.CharField(
                choices=[
                    ('IDLE', 'Idle'),
                    ('RUNNING', 'Running'),
                    ('COMPLETED', 'Completed'),
                    ('FAILED', 'Failed'),
                ],
                default='IDLE',
                max_length=20,
            ),
        ),
    ]
