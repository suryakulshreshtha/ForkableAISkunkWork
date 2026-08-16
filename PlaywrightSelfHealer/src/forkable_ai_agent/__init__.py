"""PlaywrightSelfHealer - self-healing Playwright tests that run offline.

Everything in this package is designed to run on a machine with the network
cable pulled out. The only network endpoints ever contacted are loopback
addresses: the local Ollama daemon and the local demo application.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
