#!/bin/bash
set -e

MW_CONF="/var/www/mediawiki/w/LocalSettings.php"

# Run MW database updates
php /var/www/mediawiki/w/maintenance/run.php update.php --quick --conf "$MW_CONF"

# Seed test pages
php /var/www/mediawiki/w/maintenance/run.php edit "Test/Smoke_Test" "Initial test page for integration tests." --summary="Integration test seed" --conf "$MW_CONF" 2>/dev/null || true

# Create a test image in the images directory
mkdir -p /var/www/mediawiki/w/images/0/00
echo "test image content" > /var/www/mediawiki/w/images/0/00/Test_image.txt

echo "Test pages seeded"
