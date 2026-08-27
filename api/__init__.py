"""
Spark API: a web layer over the existing risk engine.

How the package is laid out, outermost first:

``routes``        which URL maps to which handler, and nothing else
``controllers``   the handlers: read input, call a service, shape the answer
``services``      the work itself, with no knowledge of HTTP
``models``        the database tables
``database``      the engine, the session factory and schema creation
``validators``    the request and response shapes
``dependencies``  who is calling, how often, and what they may touch
``middleware``    origins, headers, timing and error shaping
``types``         shared types that are neither a table nor a request shape
``lib``           low-level pieces: keys, sessions, cache, rate limiting
``utils``         small helpers that know nothing about the domain
``config``        settings, read from the environment

``main`` only assembles these into a FastAPI application.
"""

__version__ = "1.0.0"
