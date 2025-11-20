from django.urls import include, path
from rest_framework.routers import SimpleRouter

from graflow.api.views import FlowTypeViewSet, FlowViewSet

app_name = "graflow"

router = SimpleRouter()
router.register(r"flows", FlowViewSet, basename="flow")
router.register(r"flow-types", FlowTypeViewSet, basename="flow-type")

urlpatterns = [
    path("", include(router.urls)),
]
