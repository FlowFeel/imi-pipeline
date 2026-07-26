#!/bin/bash
set -e

MW_CONF="/var/www/mediawiki/w/LocalSettings.php"

# Create a bot account for API tests
php /var/www/mediawiki/w/maintenance/run.php createAndPromote --sysop TestBot testpass --conf "$MW_CONF" 2>/dev/null || true

# Ensure the bot has API access
php /var/www/mediawiki/w/maintenance/run.php edit User:TestBot "# Test Bot Account" --summary="Create bot user page" --conf "$MW_CONF" 2>/dev/null || true

echo "Test admin created: TestBot / testpass"
