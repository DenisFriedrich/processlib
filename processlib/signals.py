from logging import getLogger

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import pre_migrate

from processlib import autodiscover_flows
from .flow import get_flows

logger = getLogger(__name__)


def create_flow_permissions(app_config, **kwargs):
    logger.info("creating permissions")
    for label, flow in get_flows():
        process_content_type = ContentType.objects.get_for_model(flow.process_model)
        if flow.permission is not None and flow.auto_create_permission:
            # split like django
            app_label, codename = flow.permission.split('.', 1)
            # app_label has to match the content type app_label so ...
            if app_label != process_content_type.app_label:
                raise ValueError(
                    "The permission {} has an app label {} that "
                    "does not match the process model's app_label {}".format(
                        flow.permission, app_label, process_content_type.app_label,
                    )
                )
            Permission.objects.update_or_create(
                content_type=process_content_type,
                codename=codename,
                defaults={'name': str(flow)},
            )
        activity_content_type = ContentType.objects.get_for_model(flow.activity_model)
        for activity_name, activity in flow._activities.items():
            activity_kwargs = flow._activity_kwargs[activity_name]
            permission = activity_kwargs.get('permission', None)
            if not activity_kwargs.get('auto_create_permission', True) or permission is None:
                continue

            # split like django
            app_label, codename = permission.split('.', 1)
            if app_label != activity_content_type.app_label:
                raise ValueError(
                    "The permission {} has an app label {} that "
                    "does not match the activity model's app_label {}".format(
                        permission, app_label, activity_content_type.app_label,
                    )
                )

            name = activity_kwargs.get('verbose_name', '') or activity_name
            Permission.objects.update_or_create(
                content_type=activity_content_type,
                codename=codename,
                defaults={'name': "{} - {}".format(str(flow), str(name))},
            )


pre_migrate.connect(lambda *args, **kwargs: autodiscover_flows(),
                    dispatch_uid="processlib.signals.autodiscover_flows")
