from rest_framework.throttling import UserRateThrottle


class FlowCreationThrottle(UserRateThrottle):
    """
    Throttle flow creation to prevent excessive flow creations.
    """

    scope = "flow_creation"


class FlowResumeThrottle(UserRateThrottle):
    """
    Throttle flow resumption to prevent excessive flow resumptions.
    """

    scope = "flow_resume"
