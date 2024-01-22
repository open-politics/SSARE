# Use an official Python runtime as a parent image
FROM python:3.9

# Set the working directory in the container to /app
WORKDIR /app

# Install any needed packages specified in requirements.txt
COPY SSARE/app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container at /app
COPY SSARE/app/ .

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Run the application using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
