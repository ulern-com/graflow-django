from rest_framework.throttling import UserRateThrottle


class FlowCreationThrottle(UserRateThrottle):
    """
    Throttle flow creation to prevent excessive flow creations.

    Default rate: 100 per hour per user.
    Can be overridden via REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['flow_creation'].
    """

    scope = "flow_creation"

    def get_rate(self):
        """
        Return the default rate for flow creation.

        Returns a default rate that works without settings configuration.
        Can be overridden by setting REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['flow_creation'].
        """
        # Check if rate is defined in settings first (DRF's default behavior)
        # If not found, return our default rate
        from django.conf import settings

        throttle_rates = getattr(settings, "REST_FRAMEWORK", {}).get("DEFAULT_THROTTLE_RATES", {})
        if self.scope in throttle_rates:
            return throttle_rates[self.scope]

        # Default: 100 requests per hour
        return "100/hour"


class FlowResumeThrottle(UserRateThrottle):
    """
    Throttle flow resumption to prevent excessive flow resumptions.

    Default rate: 300 per hour per user.
    Can be overridden via REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['flow_resume'].
    """

    scope = "flow_resume"

    def get_rate(self):
        """
        Return the default rate for flow resumption.

        Returns a default rate that works without settings configuration.
        Can be overridden by setting REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['flow_resume'].
        """
        # Check if rate is defined in settings first (DRF's default behavior)
        # If not found, return our default rate
        from django.conf import settings

        throttle_rates = getattr(settings, "REST_FRAMEWORK", {}).get("DEFAULT_THROTTLE_RATES", {})
        if self.scope in throttle_rates:
            return throttle_rates[self.scope]

        # Default: 300 requests per hour (higher than creation since resume is more interactive)
        return "300/hour"
