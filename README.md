# Dummy Device Driver

This package demonstrates how to develop a device driver that can be integrated with the `cgse` framework. It provides a
Dummy Control Server that connects to a Dummy Device, which acts as a data acquisition simulator.

## Features

- Dummy Control Server for testing and development
- Simulated device for data acquisition
- Example implementation for integration with the `cgse` framework

## Directory Structure

- `cgse_dummy/`
    - `cgse_explore.py` - implements the `show_processes()` function used by the `cgse show procs` command
    - `cgse_services.py` - Service definitions for the dummy device, provides the `dummy` sub-command for the `cgse`
    - `dummy_cs.py` - implementation of the synchronous control server
    - `dummy_acs.py` - implementation of the asynchronous control server (experimental)
    - `dummy_dev.py` - implementation of the synchronous device driver
    - `dummy_adev.py` - implementation of the asynchronous device driver (experimental)
    - `dummy_sim.py` - Simulation logic for the dummy device
    - `sim_data.py` - Simulation data generation
    - `settings.yaml` - Configuration file with port numbers and other settings for the Dummy device and Dummy control
      server

## Developer Installation

Clone the repository and install the package:

```bash
git clone git@github.com:IvS-KULeuven/cgse-dummy.git
cd cgse-dummy
```

## User installation

This package is available on PyPI, but it is not intended for end users. Instead, it serves as a reference
implementation for developers who wish to inspect the source code and learn how to create external device packages that
integrate with the `cgse` framework.

## Requirements

- Python 3.10+
- Any additional dependencies listed in the `pyproject.toml` file.

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request.

## License

MIT

## Contact

For questions or support, please raise an issue.
