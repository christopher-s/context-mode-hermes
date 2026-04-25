from setuptools import setup, find_packages

setup(
    name="context-mode-hermes",
    version="1.0.0",
    packages=find_packages(),
    python_requires=">=3.9",
    entry_points={
        "hermes_agent.plugins": [
            "context-mode = context_mode_hermes:register",
        ],
    },
)
