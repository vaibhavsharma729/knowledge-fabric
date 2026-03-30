#!/bin/bash
# Copy nginx config and start nginx, then start Streamlit.
# nginx listens on 8501 (App Runner's port) and proxies to Streamlit on 8502.

set -e

# Install nginx config
cp /app/nginx.conf /etc/nginx/conf.d/streamlit.conf
# Remove default nginx site so it doesn't conflict
rm -f /etc/nginx/sites-enabled/default

# Start nginx in background
nginx &

# Start Streamlit on internal port 8502
exec streamlit run app.py \
    --server.port=8502 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.enableWebsocketCompression=false
