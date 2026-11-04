<?php
/**
 * IMI Diagnostics — test-bed mu-plugin for Docker integration tests.
 *
 * Same API as the production mu-plugin but with a fixed test token.
 * Provides raw SQL access bypassing wp_slash() for parity testing.
 *
 * Access via: http://localhost:18090/?imi_diag=1&action=status&token=imi_test_token
 *
 * @package IMI_Diagnostics
 * @version 1.0.0
 */

// Enable application passwords over HTTP in test environments
add_filter('wp_is_application_passwords_available', '__return_true');
add_filter('application_password_is_api_request', '__return_true');

add_action('init', function() {
    if (!isset($_GET['imi_diag'])) {
        return;
    }

    // Test token — only valid in Docker test environment
    $secret_token   = 'imi_test_token';
    $provided_token = isset($_GET['token']) ? sanitize_text_field($_GET['token']) : '';
    if ($provided_token !== $secret_token) {
        http_response_code(403);
        header('Content-Type: application/json');
        echo json_encode(['error' => 'Invalid token']);
        exit;
    }

    header('Content-Type: application/json');

    global $wpdb;

    $action  = isset($_GET['action']) ? sanitize_text_field($_GET['action']) : 'status';
    $page_id = isset($_GET['page_id']) ? intval($_GET['page_id']) : 0;

    switch ($action) {
        case 'status':
            echo json_encode([
                'status'      => 'ok',
                'version'     => '1.0.0',
                'wp_version'  => get_bloginfo('version'),
                'php_version' => PHP_VERSION,
                'elementor'   => class_exists('\Elementor\Plugin'),
            ], JSON_PRETTY_PRINT);
            break;

        case 'raw_meta':
            $key = isset($_GET['key']) ? sanitize_text_field($_GET['key']) : '_elementor_data';
            $val = $wpdb->get_var($wpdb->prepare(
                "SELECT meta_value FROM {$wpdb->postmeta} WHERE post_id = %d AND meta_key = %s",
                $page_id, $key
            ));
            echo json_encode([
                'page_id' => $page_id,
                'key'     => $key,
                'length'  => $val ? strlen($val) : 0,
                'value'   => $val,
            ], JSON_PRETTY_PRINT);
            break;

        case 'set_elementor':
            $json = file_get_contents('php://input');
            $data = json_decode($json, true);
            if (!isset($data['_elementor_data'])) {
                http_response_code(400);
                echo json_encode(['error' => 'Missing _elementor_data in JSON body']);
                exit;
            }
            $new_data = $data['_elementor_data'];
            $old_raw = $wpdb->get_var($wpdb->prepare(
                "SELECT meta_value FROM {$wpdb->postmeta} WHERE post_id = %d AND meta_key = '_elementor_data'",
                $page_id
            ));
            // Raw SQL UPDATE — bypasses wp_slash()
            $affected = $wpdb->query($wpdb->prepare(
                "UPDATE {$wpdb->postmeta} SET meta_value = %s WHERE post_id = %d AND meta_key = '_elementor_data'",
                $new_data, $page_id
            ));
            $verify = $wpdb->get_var($wpdb->prepare(
                "SELECT meta_value FROM {$wpdb->postmeta} WHERE post_id = %d AND meta_key = '_elementor_data'",
                $page_id
            ));
            echo json_encode([
                'status'            => $affected ? 'updated' : 'failed',
                'page_id'           => $page_id,
                'old_length'        => $old_raw ? strlen($old_raw) : 0,
                'new_length'         => strlen($new_data),
                'verify_length'     => strlen($verify),
                'verify_json_valid' => (json_decode($verify, true) !== null),
            ], JSON_PRETTY_PRINT);
            break;

        case 'backup':
            $post = get_post($page_id);
            $meta_rows = $wpdb->get_results($wpdb->prepare(
                "SELECT meta_key, meta_value FROM {$wpdb->postmeta} WHERE post_id = %d",
                $page_id
            ));
            $flat_meta = [];
            foreach ($meta_rows as $row) {
                $flat_meta[$row->meta_key] = $row->meta_value;
            }
            echo json_encode([
                'backup_time' => current_time('mysql'),
                'page' => [
                    'ID'            => $post->ID,
                    'post_title'    => $post->post_title,
                    'post_content'  => $post->post_content,
                    'post_status'   => $post->post_status,
                    'post_type'     => $post->post_type,
                ],
                'meta' => $flat_meta,
            ], JSON_PRETTY_PRINT);
            break;

        case 'restore_elementor':
            $source_meta_id = isset($_GET['source_meta_id']) ? intval($_GET['source_meta_id']) : 0;
            if (!$source_meta_id) {
                http_response_code(400);
                echo json_encode(['error' => 'Missing source_meta_id']);
                exit;
            }
            $source = $wpdb->get_row($wpdb->prepare(
                "SELECT meta_value FROM {$wpdb->postmeta} WHERE meta_id = %d",
                $source_meta_id
            ));
            if (!$source) {
                http_response_code(404);
                echo json_encode(['error' => 'Source not found']);
                exit;
            }
            $affected = $wpdb->query($wpdb->prepare(
                "UPDATE {$wpdb->postmeta} SET meta_value = %s WHERE post_id = %d AND meta_key = '_elementor_data'",
                $source->meta_value, $page_id
            ));
            $verify = $wpdb->get_var($wpdb->prepare(
                "SELECT meta_value FROM {$wpdb->postmeta} WHERE post_id = %d AND meta_key = '_elementor_data'",
                $page_id
            ));
            echo json_encode([
                'status'             => $affected ? 'restored' : 'failed',
                'page_id'            => $page_id,
                'source_meta_id'     => $source_meta_id,
                'source_length'      => strlen($source->meta_value),
                'verify_length'      => strlen($verify),
                'verify_matches_source' => ($verify === $source->meta_value),
                'verify_json_valid'  => (json_decode($verify, true) !== null),
            ], JSON_PRETTY_PRINT);
            break;

        case 'sql':
            $query = isset($_GET['q']) ? stripslashes($_GET['q']) : '';
            if (!$query || stripos(trim($query), 'SELECT') !== 0) {
                http_response_code(400);
                echo json_encode(['error' => 'Only SELECT queries allowed']);
                exit;
            }
            $results = $wpdb->get_results($query);
            echo json_encode([
                'query'   => $query,
                'results' => count($results),
                'data'    => $results,
            ], JSON_PRETTY_PRINT);
            break;

        case 'page_meta':
            $meta_rows = $wpdb->get_results($wpdb->prepare(
                "SELECT meta_key, meta_value FROM {$wpdb->postmeta} WHERE post_id = %d",
                $page_id
            ));
            $result = [];
            foreach ($meta_rows as $row) {
                $result[$row->meta_key] = [
                    'length'  => strlen($row->meta_value),
                    'is_json' => (json_decode($row->meta_value, true) !== null),
                ];
            }
            echo json_encode(['page_id' => $page_id, 'meta' => $result], JSON_PRETTY_PRINT);
            break;

        case 'create_fixture_page':
            // Create a page with known Elementor data for testing
            $json = file_get_contents('php://input');
            $data = json_decode($json, true);
            $title = isset($data['title']) ? $data['title'] : 'Test Fixture Page';
            $elementor_data = isset($data['_elementor_data']) ? $data['_elementor_data'] : '[]';

            // Create the page via wp_insert_post (within WP context)
            $page_id = wp_insert_post([
                'post_title'   => $title,
                'post_status'   => 'publish',
                'post_type'     => 'page',
                'post_content'  => '<!-- Elementor test page -->',
            ]);

            if (!$page_id || is_wp_error($page_id)) {
                http_response_code(500);
                echo json_encode(['error' => 'Failed to create page']);
                exit;
            }

            // Set Elementor meta via raw SQL
            $wpdb->query($wpdb->prepare(
                "INSERT INTO {$wpdb->postmeta} (post_id, meta_key, meta_value)
                 VALUES (%d, '_elementor_data', %s)
                 ON DUPLICATE KEY UPDATE meta_value = VALUES(meta_value)",
                $page_id, $elementor_data
            ));
            // Set edit mode
            $wpdb->query($wpdb->prepare(
                "INSERT INTO {$wpdb->postmeta} (post_id, meta_key, meta_value)
                 VALUES (%d, '_elementor_edit_mode', 'builder')
                 ON DUPLICATE KEY UPDATE meta_value = VALUES(meta_value)",
                $page_id
            ));
            $wpdb->query($wpdb->prepare(
                "INSERT INTO {$wpdb->postmeta} (post_id, meta_key, meta_value)
                 VALUES (%d, '_elementor_template_type', 'wp-page')
                 ON DUPLICATE KEY UPDATE meta_value = VALUES(meta_value)",
                $page_id
            ));

            echo json_encode([
                'status'  => 'created',
                'page_id' => $page_id,
                'title'   => $title,
                'elementor_data_length' => strlen($elementor_data),
            ], JSON_PRETTY_PRINT);
            break;

        default:
            http_response_code(400);
            echo json_encode(['error' => 'Unknown action: ' . $action]);
    }

    exit;
});
