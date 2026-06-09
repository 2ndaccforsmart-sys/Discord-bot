# Use the official Playwright jammy container layout (comes with system dependencies)
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Establish workspace layer
WORKDIR /app

# Disable python output buffering to see logs in real-time
ENV PYTHONUNBUFFERED=1

# Copy dependency definition
COPY requirements.txt /app/

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download and install the specific Chromium browser binary matching the installed Playwright version
RUN playwright install chromium

# Copy the rest of the application files
COPY . /app

# Run the final launch command target sequence
CMD ["xvfb-run", "--server-args=-screen 0 1280x720x24", "python", "bot.py"]
