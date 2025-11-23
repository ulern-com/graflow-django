# Generated manually for graflow Django app
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Store",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("prefix", models.TextField()),
                ("key", models.TextField()),
                ("value", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("ttl_minutes", models.IntegerField(blank=True, null=True)),
            ],
            options={
                "db_table": "store",
            },
        ),
        migrations.CreateModel(
            name="Checkpoint",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("thread_id", models.TextField()),
                ("checkpoint_ns", models.TextField(default="")),
                ("checkpoint_id", models.TextField()),
                ("parent_checkpoint_id", models.TextField(blank=True, null=True)),
                ("type", models.TextField(blank=True, null=True)),
                ("checkpoint", models.JSONField()),
                ("metadata", models.JSONField(default=dict)),
            ],
            options={
                "db_table": "checkpoints",
            },
        ),
        migrations.CreateModel(
            name="CheckpointBlob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("thread_id", models.TextField()),
                ("checkpoint_ns", models.TextField(default="")),
                ("channel", models.TextField()),
                ("version", models.TextField()),
                ("type", models.TextField()),
                ("blob", models.BinaryField(blank=True, null=True)),
            ],
            options={
                "db_table": "checkpoint_blobs",
            },
        ),
        migrations.CreateModel(
            name="CheckpointWrite",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("thread_id", models.TextField()),
                ("checkpoint_ns", models.TextField(default="")),
                ("checkpoint_id", models.TextField()),
                ("task_id", models.TextField()),
                ("idx", models.IntegerField()),
                ("channel", models.TextField()),
                ("type", models.TextField(blank=True, null=True)),
                ("blob", models.BinaryField(blank=True, null=True)),
                ("task_path", models.TextField(default="")),
            ],
            options={
                "db_table": "checkpoint_writes",
            },
        ),
        migrations.CreateModel(
            name="CacheEntry",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("namespace", models.TextField()),
                ("key", models.TextField()),
                ("value_encoding", models.TextField()),
                ("value_data", models.BinaryField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "graflow_cache_entry",
            },
        ),
        migrations.CreateModel(
            name="Flow",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("app_name", models.CharField(help_text="Application name", max_length=255)),
                (
                    "flow_type",
                    models.CharField(
                        help_text="Type of the flow (i.e. graph name)", max_length=255
                    ),
                ),
                (
                    "graph_version",
                    models.CharField(
                        help_text="Version of the graph defining the flow", max_length=50
                    ),
                ),
                (
                    "display_name",
                    models.CharField(
                        blank=True,
                        help_text="User-friendly name for this flow",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "cover_image_url",
                    models.URLField(blank=True, help_text="Image URL for this flow", null=True),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("interrupted", "Interrupted"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="pending",
                        max_length=255,
                    ),
                ),
                ("error_message", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_resumed_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="flows",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "graflow_flow",
            },
        ),
        migrations.AddIndex(
            model_name="store",
            index=models.Index(fields=["prefix"], name="store_prefix_idx"),
        ),
        migrations.AddIndex(
            model_name="store",
            index=models.Index(fields=["expires_at"], name="store_expires_at_idx"),
        ),
        migrations.AddConstraint(
            model_name="store",
            constraint=models.UniqueConstraint(
                fields=("prefix", "key"), name="store_prefix_key_uniq"
            ),
        ),
        migrations.AddIndex(
            model_name="checkpoint",
            index=models.Index(fields=["thread_id"], name="checkpoints_thread_id_idx"),
        ),
        migrations.AddConstraint(
            model_name="checkpoint",
            constraint=models.UniqueConstraint(
                fields=("thread_id", "checkpoint_ns", "checkpoint_id"),
                name="checkpoint_thread_ns_id_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="checkpointblob",
            index=models.Index(fields=["thread_id"], name="checkpoint_blobs_thread_id_idx"),
        ),
        migrations.AddConstraint(
            model_name="checkpointblob",
            constraint=models.UniqueConstraint(
                fields=("thread_id", "checkpoint_ns", "channel", "version"),
                name="checkpointblob_thread_ns_channel_version_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="checkpointwrite",
            index=models.Index(fields=["thread_id"], name="checkpoint_writes_thrd_id_idx"),
        ),
        migrations.AddConstraint(
            model_name="checkpointwrite",
            constraint=models.UniqueConstraint(
                fields=("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"),
                name="checkpointwrite_thread_ns_id_task_idx_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="cacheentry",
            index=models.Index(fields=["namespace"], name="cache_namespace_idx"),
        ),
        migrations.AddIndex(
            model_name="cacheentry",
            index=models.Index(fields=["expires_at"], name="cache_expires_at_idx"),
        ),
        migrations.AddConstraint(
            model_name="cacheentry",
            constraint=models.UniqueConstraint(
                fields=("namespace", "key"), name="cacheentry_namespace_key_uniq"
            ),
        ),
        migrations.AddIndex(
            model_name="flow",
            index=models.Index(
                fields=["user", "app_name", "flow_type"],
                name="graflow_flow_user_app_name_flow_type_idx",
            ),
        ),
    ]
