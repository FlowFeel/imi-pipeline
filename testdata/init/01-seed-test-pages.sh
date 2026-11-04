#!/bin/bash
set -e

# Find LocalSettings.php
MW_CONF=$(find /var/www /etc -name "LocalSettings.php" -type f 2>/dev/null | head -1)
if [ -z "$MW_CONF" ]; then
    echo "ERROR: LocalSettings.php not found anywhere in /var/www or /etc"
    echo "Searching /var/www/mediawiki structure:"
    ls -la /var/www/mediawiki/w/ 2>/dev/null || echo "  /var/www/mediawiki/w/ does not exist"
    ls -la /var/www/mediawiki/ 2>/dev/null || echo "  /var/www/mediawiki/ does not exist"
    ls -la /var/www/ 2>/dev/null
    exit 1
fi
echo "Found LocalSettings.php at: $MW_CONF"

# Run MW database updates
php /var/www/mediawiki/w/maintenance/run.php update.php --quick --conf "$MW_CONF"

# Seed test pages
php /var/www/mediawiki/w/maintenance/run.php edit "Test/Smoke_Test" "Initial test page for integration tests." --summary="Integration test seed" --conf "$MW_CONF" 2>/dev/null || true

# Create a test image in the images directory
mkdir -p /var/www/mediawiki/w/images/0/00
echo "test image content" > /var/www/mediawiki/w/images/0/00/Test_image.txt

echo "Test pages seeded"
