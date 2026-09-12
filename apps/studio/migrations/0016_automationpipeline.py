from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('studio', '0015_remove_6_animation_styles'),
    ]

    operations = [
        migrations.CreateModel(
            name='AutomationPipeline',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='My Automation', max_length=255)),
                ('steps_config', models.JSONField(default=list)),
                ('status', models.CharField(
                    choices=[
                        ('IDLE', 'Idle'),
                        ('RUNNING', 'Running'),
                        ('COMPLETED', 'Completed'),
                        ('FAILED', 'Failed'),
                        ('PAUSED', 'Paused'),
                    ],
                    default='IDLE',
                    max_length=20,
                )),
                ('current_step_index', models.IntegerField(default=0)),
                ('log', models.TextField(blank=True, default='')),
                ('result_download_job_id', models.IntegerField(blank=True, null=True)),
                ('result_lyric_project_id', models.IntegerField(blank=True, null=True)),
                ('result_publishing_job_id', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Automation Pipeline',
                'ordering': ['-created_at'],
            },
        ),
    ]
