#!/bin/bash
set -e

# Find LocalSettings.php
MW_CONF=$(find /var/www /etc -name "LocalSettings.php" -type f 2>/dev/null | head -1)
if [ -z "$MW_CONF" ]; then
    echo "ERROR: LocalSettings.php not found"
    exit 1
fi
echo "Found LocalSettings.php at: $MW_CONF"

# Create a bot account for API tests
php /var/www/mediawiki/w/maintenance/run.php createAndPromote --sysop TestBot testpass --conf "$MW_CONF" 2>/dev/null || true

# Ensure the bot has API access
php /var/www/mediawiki/w/maintenance/run.php edit User:TestBot "# Test Bot Account" --summary="Create bot user page" --conf "$MW_CONF" 2>/dev/null || true

echo "Test admin created: TestBot / testpass"
