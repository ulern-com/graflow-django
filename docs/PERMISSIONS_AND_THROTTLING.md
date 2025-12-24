# Permissions and Throttling in Graflow

Graflow provides fine-grained, per-flow-type permissions and throttling capabilities. This allows you to control access and rate limiting at the flow type level, enabling multi-tenant applications, subscription-based access, and abuse prevention.

---

## Table of Contents

1. [Overview](#overview)
2. [Permissions](#permissions)
3. [Throttling](#throttling)
4. [Configuration](#configuration)
5. [Examples](#examples)
6. [Considerations and Best Practices](#considerations-and-best-practices)
7. [API Behavior](#api-behavior)

---

## Overview

### What are Permissions and Throttling?

**Permissions** control **who** can access which flows. They determine whether a user has the right to create, view, update, delete, or resume flows of a specific type.

**Throttling** controls **how frequently** users can perform operations. It limits the rate of requests to prevent abuse, manage resource usage, and implement usage tiers.

### Why are they Needed?

- **Multi-tenancy**: Different applications or tenants may need different access rules
- **Subscription Tiers**: Premium users might have access to certain flow types that free users don't
- **Security**: Restrict sensitive flows to authorized users only
- **Resource Management**: Prevent API abuse and manage server load
- **Business Logic**: Some flows might be created by admins but resumed by end users

### How They Work

Permissions and throttling are configured at the **FlowType** level (not per-flow), which means:

- All flows of the same type share the same permission/throttle rules
- You can have different rules for different flow types
- Rules can be updated by modifying the `FlowType` model (affects new flows immediately)
- Each flow type can have separate rules for:
  - **CRUD operations**: list, create, retrieve, destroy, cancel
  - **Resume operations**: resuming interrupted flows

---

## Permissions

### Default Behavior

By default, all flow types use `rest_framework.permissions.IsAuthenticated` for both CRUD and resume operations. This means:

- Users must be authenticated to access any flow operations
- Anonymous users are denied access (unless `GRAFLOW_REQUIRE_AUTHENTICATION = False`)

### Separating CRUD and Resume Permissions

Graflow separates permissions into two categories:

1. **CRUD Permission** (`crud_permission_class`): Controls access to:
   - `POST /flows/` (create)
   - `GET /flows/` (list)
   - `GET /flows/{id}/` (retrieve)
   - `DELETE /flows/{id}/` (destroy)
   - `POST /flows/{id}/cancel/` (cancel)
   - `GET /flows/most-recent/` (most recent)

2. **Resume Permission** (`resume_permission_class`): Controls access to:
   - `POST /flows/{id}/resume/` (resume)

This separation enables use cases like:
- Admin creates flows, users resume them
- Public flows (AllowAny for CRUD), but only authenticated users can resume
- Flows visible to all authenticated users, but only premium users can resume

### Permission Class Path Format

Permissions are specified as string paths in one of two formats:

- **Colon format**: `module.path:ClassName` (recommended)
  - Example: `myapp.permissions:SubscriptionPermission`
- **Dot format**: `module.path.ClassName` (for compatibility with DRF defaults)
  - Example: `rest_framework.permissions.IsAuthenticated`

Both formats are supported for flexibility.

### When Permissions are Checked

Permissions are checked at two levels:

1. **View-level** (`has_permission()`): For actions that don't have a specific object:
   - `create`: Checks if user can create flows of this type
   - `list`: Checks if user can list flows (then filters by object permissions)

2. **Object-level** (`has_object_permission()`): For actions on specific flows:
   - `retrieve`: Checks if user can view this specific flow
   - `destroy`: Checks if user can delete this specific flow
   - `cancel`: Checks if user can cancel this specific flow
   - `resume`: Checks if user can resume this specific flow

For `list` operations, Graflow automatically filters results to only include flows where the user has object-level permission.

### Creating Custom Permission Classes

Custom permission classes must inherit from DRF's `BasePermission` and implement `has_permission()` and/or `has_object_permission()`.

**Example: Flow Type-Specific Permission**

```python
# myapp/permissions.py
from rest_framework.permissions import BasePermission
from graflow.models.flows import Flow

class AllowOnlyPremiumFlowPermission(BasePermission):
    """
    Only allow access to flows of type 'premium_workflow'.
    """
    
    def has_permission(self, request, view):
        """Check permission at view level (for create, list)."""
        if view.action == "create":
            # Check if the requested flow_type is allowed
            flow_type = request.data.get("flow_type")
            return flow_type == "premium_workflow"
        return True  # Allow list (filtering happens in queryset)
    
    def has_object_permission(self, request, view, obj):
        """Check permission for a specific flow object."""
        if isinstance(obj, Flow):
            # Only allow access if flow is of the premium type
            return obj.flow_type == "premium_workflow"
        return False
```

**Example: Subscription-Based Permission**

```python
# myapp/permissions.py
from rest_framework.permissions import BasePermission

class SubscriptionPermission(BasePermission):
    """
    Check if user has active subscription.
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Check if user has active subscription
        return hasattr(request.user, 'subscription') and request.user.subscription.is_active
    
    def has_object_permission(self, request, view, obj):
        # Same check for object-level
        return self.has_permission(request, view)
```

**Example: Owner-Only Permission**

```python
# myapp/permissions.py
from rest_framework.permissions import BasePermission

class OwnerOnlyPermission(BasePermission):
    """
    Only allow access to flows owned by the requesting user.
    """
    
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Flow):
            # Only allow if user owns the flow
            return obj.user == request.user
        return False
```

---

## Throttling

### Default Behavior

Graflow provides default throttling for flow operations:

- **FlowCreationThrottle**: 100 requests per hour per user (for `create` action)
- **FlowResumeThrottle**: 300 requests per hour per user (for `resume` action)
- **No throttling** for other operations (retrieve, list, destroy, cancel) unless configured

These defaults work out of the box without any configuration.

### Separating CRUD and Resume Throttling

Like permissions, throttling is separated:

1. **CRUD Throttle** (`crud_throttle_class`): Controls rate limiting for:
   - `create`, `list`, `retrieve`, `destroy`, `cancel`, `most_recent`

2. **Resume Throttle** (`resume_throttle_class`): Controls rate limiting for:
   - `resume`

This allows different rate limits for different operations (e.g., stricter limits on creation vs. resume).

### Throttle Class Path Format

Same format as permissions:
- **Colon format**: `module.path:ClassName` (e.g., `myapp.throttling:PremiumThrottle`)
- **Dot format**: `module.path.ClassName` (e.g., `graflow.api.throttling.FlowCreationThrottle`)

### Overriding Default Rates

You can override the default throttle rates globally via Django settings:

```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'flow_creation': '50/hour',  # Override default 100/hour
        'flow_resume': '200/hour',   # Override default 300/hour
    }
}
```

Or specify custom rates for custom throttle scopes:

```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'premium_user': '1000/hour',
        'free_user': '10/hour',
    }
}
```

### Creating Custom Throttle Classes

Custom throttle classes must inherit from DRF's throttle classes (usually `UserRateThrottle` or `AnonRateThrottle`) and specify a `scope`.

**Example: Tiered Throttling Based on Subscription**

```python
# myapp/throttling.py
from rest_framework.throttling import UserRateThrottle

class PremiumUserThrottle(UserRateThrottle):
    """
    Higher rate limit for premium users.
    """
    scope = "premium_user"
    
    def get_rate(self):
        """Return rate based on user's subscription tier."""
        from django.conf import settings
        
        throttle_rates = getattr(settings, "REST_FRAMEWORK", {}).get("DEFAULT_THROTTLE_RATES", {})
        if self.scope in throttle_rates:
            return throttle_rates[self.scope]
        
        # Default: 1000 requests per hour for premium users
        return "1000/hour"
    
    def allow_request(self, request, view):
        """Only apply to premium users."""
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user has premium subscription
        if not (hasattr(request.user, 'subscription') and request.user.subscription.tier == 'premium'):
            return False
        
        return super().allow_request(request, view)


class FreeUserThrottle(UserRateThrottle):
    """
    Lower rate limit for free users.
    """
    scope = "free_user"
    
    def get_rate(self):
        """Return rate for free users."""
        from django.conf import settings
        
        throttle_rates = getattr(settings, "REST_FRAMEWORK", {}).get("DEFAULT_THROTTLE_RATES", {})
        if self.scope in throttle_rates:
            return throttle_rates[self.scope]
        
        # Default: 10 requests per hour for free users
        return "10/hour"
```

**Example: Per-Flow-Type Throttling**

```python
# myapp/throttling.py
from rest_framework.throttling import UserRateThrottle

class ExpensiveFlowThrottle(UserRateThrottle):
    """
    Stricter throttling for expensive/compute-intensive flows.
    """
    scope = "expensive_flow"
    
    def get_rate(self):
        """Very low rate for expensive operations."""
        return "5/hour"  # Only 5 requests per hour
```

### Throttle Scope

Throttling uses **per-user buckets**, meaning:
- Each authenticated user has their own throttle counter
- Different users don't affect each other's rate limits
- Anonymous users (if allowed) share a single bucket
- Counters reset based on the time window (e.g., sliding window for hourly limits)

### Operations Without Throttling

By default, the following operations have **no throttling** unless configured:
- `retrieve` (GET `/flows/{id}/`)
- `list` (GET `/flows/`) when no `flow_type` parameter is provided
- `destroy` (DELETE `/flows/{id}/`)
- `cancel` (POST `/flows/{id}/cancel/`)
- `stats` (GET `/flows/stats/`)

To throttle these operations, configure a custom `crud_throttle_class` for the flow type.

---

## Configuration

### Via Django Admin

1. Navigate to Django admin → "Flow Types"
2. Click on an existing flow type or create a new one
3. Set the permission/throttle class paths:
   - **CRUD Permission Class**: `myapp.permissions:CustomPermission`
   - **Resume Permission Class**: `myapp.permissions:CustomResumePermission`
   - **CRUD Throttle Class**: `myapp.throttling:CustomThrottle`
   - **Resume Throttle Class**: `myapp.throttling:CustomResumeThrottle`
4. Save the flow type

### Programmatically

```python
from graflow.models.registry import FlowType

# Create a flow type with custom permissions and throttling
flow_type = FlowType.objects.create(
    app_name="myapp",
    flow_type="premium_workflow",
    version="v1",
    builder_path="myapp.graphs:build_premium_workflow",
    state_path="myapp.graphs:PremiumWorkflowState",
    is_latest=True,
    # Permissions
    crud_permission_class="myapp.permissions:SubscriptionPermission",
    resume_permission_class="rest_framework.permissions.IsAuthenticated",
    # Throttling
    crud_throttle_class="myapp.throttling:PremiumUserThrottle",
    resume_throttle_class="myapp.throttling:PremiumUserThrottle",
)
```

### Empty/Blank Configuration

- **Permissions**: If not specified, defaults to `IsAuthenticated` for both CRUD and resume
- **Throttling**: If `crud_throttle_class` or `resume_throttle_class` is blank/empty:
  - `create` action: Uses default `FlowCreationThrottle` (100/hour)
  - `resume` action: Uses default `FlowResumeThrottle` (300/hour)
  - Other CRUD operations: No throttling

### Invalid Paths and Fallback Behavior

If a permission or throttle class path is invalid (module not found, class not found, etc.):

- **Permissions**: Falls back to `IsAuthenticated` (fail-secure)
- **Throttling**: Falls back to default throttles or no throttling (fail-open for availability)

Errors are logged but don't break the API.

---

## Examples

### Example 1: Basic Setup (Using Defaults)

```python
# No configuration needed - uses defaults
flow_type = FlowType.objects.create(
    app_name="myapp",
    flow_type="basic_flow",
    version="v1",
    builder_path="myapp.graphs:build_basic_flow",
    state_path="myapp.graphs:BasicFlowState",
    is_latest=True,
)
# Uses IsAuthenticated for both CRUD and resume
# Uses default throttling (100/hour create, 300/hour resume)
```

### Example 2: Public Flow with Authenticated Resume

```python
# Public flows (anyone can create/view), but only authenticated users can resume
flow_type = FlowType.objects.create(
    app_name="myapp",
    flow_type="public_flow",
    version="v1",
    builder_path="myapp.graphs:build_public_flow",
    state_path="myapp.graphs:PublicFlowState",
    is_latest=True,
    crud_permission_class="rest_framework.permissions.AllowAny",  # Public
    resume_permission_class="rest_framework.permissions.IsAuthenticated",  # Auth required
)
```

### Example 3: Subscription-Based Access

```python
# Only users with active subscription can access
from myapp.permissions import SubscriptionPermission
from myapp.throttling import PremiumUserThrottle

flow_type = FlowType.objects.create(
    app_name="myapp",
    flow_type="premium_workflow",
    version="v1",
    builder_path="myapp.graphs:build_premium_workflow",
    state_path="myapp.graphs:PremiumWorkflowState",
    is_latest=True,
    crud_permission_class="myapp.permissions:SubscriptionPermission",
    resume_permission_class="myapp.permissions:SubscriptionPermission",
    crud_throttle_class="myapp.throttling:PremiumUserThrottle",  # Higher limits
    resume_throttle_class="myapp.throttling:PremiumUserThrottle",
)
```

### Example 4: Admin-Created, User-Resumed Flow

```python
# Only admins can create, but any authenticated user can resume
from myapp.permissions import AdminOnlyPermission

flow_type = FlowType.objects.create(
    app_name="myapp",
    flow_type="admin_initialized_flow",
    version="v1",
    builder_path="myapp.graphs:build_admin_flow",
    state_path="myapp.graphs:AdminFlowState",
    is_latest=True,
    crud_permission_class="myapp.permissions:AdminOnlyPermission",  # Admin only
    resume_permission_class="rest_framework.permissions.IsAuthenticated",  # Any user
)
```

### Example 5: Tiered Access with Different Throttling

```python
# Free users: limited access, low throttling
# Premium users: full access, high throttling

# Flow type for free users
free_flow_type = FlowType.objects.create(
    app_name="myapp",
    flow_type="free_workflow",
    version="v1",
    builder_path="myapp.graphs:build_free_workflow",
    state_path="myapp.graphs:FreeWorkflowState",
    is_latest=True,
    crud_permission_class="rest_framework.permissions.IsAuthenticated",
    resume_permission_class="rest_framework.permissions.IsAuthenticated",
    crud_throttle_class="myapp.throttling:FreeUserThrottle",  # 10/hour
    resume_throttle_class="myapp.throttling:FreeUserThrottle",
)

# Flow type for premium users
premium_flow_type = FlowType.objects.create(
    app_name="myapp",
    flow_type="premium_workflow",
    version="v1",
    builder_path="myapp.graphs:build_premium_workflow",
    state_path="myapp.graphs:PremiumWorkflowState",
    is_latest=True,
    crud_permission_class="myapp.permissions:PremiumUserPermission",
    resume_permission_class="myapp.permissions:PremiumUserPermission",
    crud_throttle_class="myapp.throttling:PremiumUserThrottle",  # 1000/hour
    resume_throttle_class="myapp.throttling:PremiumUserThrottle",
)
```

---

## Considerations and Best Practices

### Performance

- Permission and throttle checks happen on **every request**, so keep them lightweight
- Avoid complex database queries in permission checks; cache results when possible
- Throttling uses Django's cache backend (default is in-memory); use Redis for distributed systems

### Multi-Tenancy

- Use `app_name` in combination with permissions to isolate tenants
- Consider creating tenant-specific permission classes that check `app_name`
- Flow types are scoped by `app_name`, so different tenants can have same-named flow types with different rules

### Versioning

- Permissions and throttles are configured **per FlowType version**
- When creating a new version of a flow type, you can change its permissions/throttling
- Existing flows continue using the version they were created with, so they keep the old rules
- Only new flows use the latest version's rules

### Testing

When testing custom permissions and throttles:

1. Clear cache between tests (throttling uses cache):
   ```python
   from django.core.cache import cache
   
   def setUp(self):
       cache.clear()
   ```

2. Use `override_settings` to test different throttle rates:
   ```python
   from django.test import override_settings
   
   @override_settings(
       REST_FRAMEWORK={
           'DEFAULT_THROTTLE_RATES': {'test_scope': '2/minute'}
       }
   )
   def test_custom_throttle(self):
       # Test with low rate for fast feedback
       pass
   ```

3. See `graflow/tests/test_permissions.py` and `graflow/tests/test_throttling.py` for examples

### Security

- **Fail-secure for permissions**: Invalid permission classes fall back to `IsAuthenticated`
- **Fail-open for throttling**: Invalid throttle classes fall back to no throttling (for availability)
- Always test permission logic thoroughly
- Use object-level permissions to ensure users can only access their own flows
- Consider using Django's `permission_required` decorator or DRF's `DjangoObjectPermissions` for complex scenarios

### Migration Strategy

When updating permissions/throttling for existing flow types:

1. **Create new version**: Set `is_latest=False` on old version, create new version with `is_latest=True`
2. **Gradual rollout**: New flows use new rules, existing flows keep old rules
3. **Update existing flows**: If needed, update `graph_version` on existing `Flow` instances (use caution)

### Common Pitfalls

1. **Forgetting object-level checks**: Always implement `has_object_permission()` to prevent access to other users' flows
2. **Throttle scope conflicts**: Ensure custom throttle scopes are unique and don't conflict with DRF defaults
3. **Cache configuration**: Throttling won't work correctly if cache isn't properly configured (use Redis in production)
4. **Anonymous users**: If allowing anonymous access, ensure throttling accounts for anonymous requests (use `AnonRateThrottle`)

---

## API Behavior

### Permission Failures

When a user lacks permission:

- **View-level**: Returns `403 Forbidden` (e.g., trying to create a flow type they don't have access to)
- **Object-level**: Returns `404 Not Found` (e.g., trying to access another user's flow - security through obscurity)

### Throttling Responses

When rate limit is exceeded:

- Returns `429 Too Many Requests`
- Response includes `Retry-After` header indicating when to retry
- DRF's default throttling response format is used

### List Filtering

When calling `GET /flows/` without a `flow_type` parameter:

- Graflow automatically filters results to only include flows where the user has object-level permission
- This ensures users only see flows they're allowed to access
- Different flow types may have different permission rules, so results are filtered per flow type

### Flow Type Selection

When creating or resuming flows:

- Permissions/throttles are selected based on the `flow_type` in the request (for create) or the flow's `flow_type` property (for resume)
- If the flow type is not found, falls back to defaults
- Errors are logged but don't prevent the operation (fail-secure/fail-open as described above)

---

## Further Reading

- [Django REST Framework Permissions](https://www.django-rest-framework.org/api-guide/permissions/)
- [Django REST Framework Throttling](https://www.django-rest-framework.org/api-guide/throttling/)
- [Graflow API Documentation](graflow/api/README.md)
- [Graflow Storage Documentation](graflow/storage/README.md)

