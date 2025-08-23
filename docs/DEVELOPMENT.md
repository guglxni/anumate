# Development Guide

This guide provides instructions for setting up the development environment and running the Anumate platform's services.

## Running Unit Tests

The unit tests for the shared libraries are designed to run without any external dependencies. They use in-memory fallbacks for services like Redis and the event bus.

To run the tests for all the packages, you can use the following command from the root of the project:

```bash
make test
```

## Consuming Packages

The shared libraries are packaged as Python wheels. The services will consume these packages by installing them from the `dist/` directory.

When a service needs to use a shared library, it will be added as a dependency in its `pyproject.toml` file, pointing to the local wheel file.

For example, to use the `anumate-core-config` package, a service's `pyproject.toml` would include:

```toml
[tool.poetry.dependencies]
python = "^3.11"
anumate-core-config = {path = "../packages/anumate-core-config", develop = true}
```
