#!/bin/bash
set -e

# Create a bot account for API tests
php /var/www/mediawiki/w/maintenance/run.php createAndPromote --sysop TestBot testpass 2>/dev/null || true

# Ensure the bot has API access
php /var/www/mediawiki/w/maintenance/run.php edit User:TestBot "# Test Bot Account" --summary="Create bot user page" 2>/dev/null || true

echo "Test admin created: TestBot / testpass"
