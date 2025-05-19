FROM mcr.microsoft.com/playwright:v1.52.0-noble

# Set up environment with Hebrew locale support
RUN apt-get update && \
    apt-get install -y locales && \
    sed -i -e 's/# he_IL.UTF-8 UTF-8/he_IL.UTF-8 UTF-8/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=he_IL.UTF-8

# Set locale environment variables
ENV LANG=he_IL.UTF-8
ENV LC_ALL=he_IL.UTF-8

WORKDIR /app

# Copy requirements and install dependencies in a virtual environment
COPY requirements.txt .

# Install Python dependencies using virtual environment
RUN apt-get update && \
    apt-get install -y python3-venv && \
    python3 -m venv /app/venv

# Use the virtual environment Python and pip
ENV PATH="/app/venv/bin:$PATH"

# Install dependencies in the virtual environment
RUN pip install -r requirements.txt

# Copy the test files
COPY . .

# Command to run tests (this will be overridden by Kubernetes Jobs)
CMD ["python", "-m", "pytest", "e2e/mobile/login/login_invalid_otp.py", "-v"]
