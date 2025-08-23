# Docker Infrastructure Setup Guide

This guide provides instructions for setting up Docker on various operating systems to run the Anumate platform's infrastructure services.

## macOS

1.  **Install Docker Desktop:**
    *   Download and install [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop).
    *   Follow the installation instructions to complete the setup.

2.  **Enable Rosetta (for Apple Silicon Macs):**
    *   If you are using a Mac with Apple Silicon (M1, M2, etc.), ensure that Rosetta 2 is installed. You can install it by running:
        ```bash
        softwareupdate --install-rosetta
        ```
    *   In Docker Desktop settings, go to **Features in development** and ensure that **Use Rosetta for x86/amd64 emulation on Apple Silicon** is enabled.

3.  **Verify Installation:**
    *   Open your terminal and run the following commands to verify the installation:
        ```bash
        docker --version
        docker compose version
        ```

## Windows

1.  **Install Docker Desktop with WSL 2:**
    *   Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop).
    *   The installation process will guide you through enabling the Windows Subsystem for Linux (WSL) 2, which is required.

2.  **Verify Installation:**
    *   Open your command prompt or PowerShell and run the following commands:
        ```bash
        docker --version
        docker compose version
        ```

## Linux

1.  **Install Docker Engine:**
    *   Follow the official instructions for your Linux distribution to install the Docker Engine. You can find the instructions [here](https://docs.docker.com/engine/install/).

2.  **Install Docker Compose Plugin:**
    *   Follow the official instructions to install the Docker Compose plugin. You can find the instructions [here](https://docs.docker.com/compose/install/).

3.  **Manage Docker as a non-root user:**
    *   Add your user to the `docker` group to run Docker commands without `sudo`:
        ```bash
        sudo usermod -aG docker $USER
        ```
    *   You will need to log out and log back in for this change to take effect.

4.  **Enable and start Docker service:**
    *   Enable the Docker service to start on boot and start it now:
        ```bash
        sudo systemctl enable --now docker
        ```

5.  **Verify Installation:**
    *   Open your terminal and run the following commands:
        ```bash
        docker --version
        docker compose version
        ```

## Post-installation Steps

1.  **Enable BuildKit:**
    *   BuildKit is the default builder for all Docker users. You can ensure it's enabled by setting the following environment variable:
        ```bash
        export DOCKER_BUILDKIT=1
        ```

2.  **Test with `hello-world`:**
    *   Run the `hello-world` container to confirm that Docker is working correctly:
        ```bash
        docker run hello-world
        ```

3.  **Troubleshooting:**
    *   **PATH issues:** If you get a "command not found" error, ensure that the Docker binary is in your system's PATH.
    *   **Permissions:** On Linux, if you have permission issues, make sure your user is in the `docker` group.
