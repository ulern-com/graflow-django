from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from graflow.models import Flow


class FlowFactory(DjangoModelFactory):
    class Meta:
        model = Flow

    user = None  # Will be set in tests
    flow_type = "test_flow"  # Default flow type used in tests
    app_name = "test_app"
    graph_version = "v1"