<?php
/**
 * Enable Application Passwords over non-HTTPS for test environments.
 */
add_filter('wp_is_application_passwords_available', '__return_true');
add_filter('application_password_is_api_request', '__return_true');
