#!/bin/bash

# Create cron log file if it doesn't exist
touch /var/log/cron.log

# Set permissions for cron log
chmod 644 /var/log/cron.log

# Job Creation (less frequent)
echo "*/30 * * * * root curl -s -X POST http://localhost:8089/trigger_step/produce_flags >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/30 * * * * root curl -s -X POST http://localhost:8089/trigger_step/create_scrape_jobs >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/10 * * * * root curl -s -X POST http://localhost:8089/trigger_step/create_embedding_jobs >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/10 * * * * root curl -s -X POST http://localhost:8089/trigger_step/create_entity_extraction_jobs >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/10 * * * * root curl -s -X POST http://localhost:8089/trigger_step/create_geocoding_jobs >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/20 * * * * root curl -s -X POST http://localhost:8089/trigger_step/create_classification_jobs >> /var/log/cron.log 2>&1" >> /etc/crontab

# Processing Steps (more frequent)
echo "*/2 * * * * root curl -s -X POST http://localhost:8089/trigger_step/store_raw_contents >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/2 * * * * root curl -s -X POST 'http://localhost:8089/trigger_step/generate_embeddings?batch_size=50' >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/2 * * * * root curl -s -X POST 'http://localhost:8089/trigger_step/extract_entities?batch_size=50' >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/10 * * * * root curl -s -X POST 'http://localhost:8089/trigger_step/geocode_contents?batch_size=50' >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/3 * * * * root curl -s -X POST 'http://localhost:8089/trigger_step/classify_contents?batch_size=50' >> /var/log/cron.log 2>&1" >> /etc/crontab

# Storage Steps (frequent)
echo "*/5 * * * * root curl -s -X POST http://localhost:8089/trigger_step/store_contents_with_embeddings >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/4 * * * * root curl -s -X POST http://localhost:8089/trigger_step/store_contents_with_entities >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/3 * * * * root curl -s -X POST http://localhost:8089/trigger_step/store_contents_with_geocoding >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/5 * * * * root curl -s -X POST http://localhost:8089/trigger_step/store_contents_with_classification >> /var/log/cron.log 2>&1" >> /etc/crontab
# Start cron service
service cron start

# Verify cron service status
service cron status

# Start the Uvicorn server in the background
uvicorn main:app --host 0.0.0.0 --port 8089 &

# Keep the container running by tailing the cron log
tail -f /var/log/cron.log