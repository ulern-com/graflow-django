# Persistence

LangGraph provides three types of persistence (see [LangGraph documentation](https://docs.langchain.com/oss/python/langgraph/add-memory)):

- **Checkpointer**: Stores checkpoints or snapshots of graph states (flows in our case)
  - [LangGraph Checkpointer Docs](https://docs.langchain.com/oss/python/langgraph/how-tos/checkpointing)
  - Base class: [`langgraph.checkpoint.postgres.PostgresSaver`](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/checkpoint/postgres/__init__.py)
- **Memory Store**: Provides long-term memory shared across threads (flows in our case)
  - [LangGraph Store Docs](https://docs.langchain.com/oss/python/langgraph/how-tos/store)
  - Base class: [`langgraph.store.postgres.PostgresStore`](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/store/postgres/__init__.py)
- **Node Cache**: Stores node outputs based on their inputs
  - [LangGraph Cache Docs](https://docs.langchain.com/oss/python/langgraph/how-tos/caching)
  - Base class: [`langgraph.cache.base.BaseCache`](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/cache/base.py)

LangGraph includes in-memory, SQLite, and PostgreSQL implementations for checkpoints and store. The node cache is only available as an in-memory implementation.

## Django Implementations

To provide better and more natural support for checkpoints and store within Django projects, we implemented **DjangoSaver** and **DjangoStore**, both inheriting from LangGraph's PostgreSQL implementations. This enables us to:

- Use Django models to represent database tables and leverage Django's ORM
- Add support for Django admin models, enabling viewing, debugging, and tracing
- Configure storage using Django settings instead of separate configuration files

### Implementation Details

- **DjangoSaver** ([`graflow/storage/checkpointer.py`](../storage/checkpointer.py)): Extends [`PostgresSaver`](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/checkpoint/postgres/__init__.py) to automatically use Django database settings
- **DjangoStore** ([`graflow/storage/store.py`](../storage/store.py)): Extends [`PostgresStore`](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/store/postgres/__init__.py) to automatically use Django database settings

These implementations are used in [`graflow/graphs/registry.py`](../graphs/registry.py) when `GRAFLOW_PERSISTENCE_BACKEND` is set to `'django'`.

## Node Cache

Node cache is especially useful for nodes that make LLM calls. When LLM calls are based on input state and the output can be easily reused, caching can significantly reduce API costs.

With proper time-to-live settings and ensuring that all significant parts of the input state are considered in cache key generation, we can save many LLM calls in certain applications.

**Example use case**: If a node's purpose is to generate a list of questions for a user to understand their problem, we can cache the node output. Even if the node generates questions based on an answer to another initial question, caching is beneficial if we can control the options a user can select for the initial question.

With expensive LLM calls in mind, we implemented **DjangoCache** ([`graflow/storage/cache.py`](../storage/cache.py)), a PostgreSQL-based node cache that provides persistence and can be shared across multiple application instances. It extends [`BaseCache`](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/cache/base.py) from LangGraph.

See the implementation in [`graflow/storage/cache.py`](../storage/cache.py) and its usage in [`graflow/graphs/registry.py`](../graphs/registry.py).

## Django Models

To support these three storage mechanisms with Django models, we added new models that match LangGraph's table definitions. This allows you to use Django's ORM to query and manage checkpoints, store entries, and cache entries directly.

The models are defined in [`graflow/models.py`](../models.py):
- `Checkpoint`: Stores graph state checkpoints (matches LangGraph's checkpoint table structure)
- `Store`: Stores key-value pairs for long-term memory (matches LangGraph's store table structure)
- `CacheEntry`: Stores cached node outputs (matches LangGraph's cache table structure)

These models enable:
- **Django Admin integration**: View and inspect persistence data through Django admin
- **ORM queries**: Query checkpoints, store entries, and cache entries using Django's ORM
- **Debugging and tracing**: Inspect flow state, store values, and cache hits/misses

See the model definitions in [`graflow/models.py`](../models.py) and test examples in:
- [`graflow/tests/test_checkpoint.py`](../tests/test_checkpoint.py) - DjangoSaver tests
- [`graflow/tests/test_store.py`](../tests/test_store.py) - DjangoStore tests
- [`graflow/tests/test_cache.py`](../tests/test_cache.py) - DjangoCache tests
