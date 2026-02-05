-- Comprehensive Database Update Script for Kids E-commerce Platform
-- This script updates the database schema to match the Flask models

-- Disable foreign key checks temporarily
SET FOREIGN_KEY_CHECKS = 0;

-- Update User table to match model
ALTER TABLE `user` 
ADD COLUMN IF NOT EXISTS `username` varchar(30) NOT NULL DEFAULT 'user' AFTER `id`,
MODIFY COLUMN `first_name` varchar(80) NOT NULL,
MODIFY COLUMN `last_name` varchar(80) NOT NULL,
MODIFY COLUMN `email` varchar(120) NOT NULL,
MODIFY COLUMN `password` varchar(120) NOT NULL,
MODIFY COLUMN `phone` varchar(20) NOT NULL,
MODIFY COLUMN `address` text NOT NULL,
MODIFY COLUMN `role` varchar(20) DEFAULT 'buyer',
MODIFY COLUMN `status` varchar(20) DEFAULT 'active',
MODIFY COLUMN `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
ADD COLUMN IF NOT EXISTS `two_factor_enabled` tinyint(1) DEFAULT 0,
ADD COLUMN IF NOT EXISTS `email_notifications` tinyint(1) DEFAULT 1,
ADD COLUMN IF NOT EXISTS `email_verified` tinyint(1) DEFAULT 0,
ADD COLUMN IF NOT EXISTS `verification_code` varchar(10) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `valid_id` varchar(255) DEFAULT NULL;

-- Add indexes for User table
CREATE INDEX IF NOT EXISTS `idx_user_email` ON `user` (`email`);
CREATE INDEX IF NOT EXISTS `idx_user_username` ON `user` (`username`);
CREATE INDEX IF NOT EXISTS `idx_user_status` ON `user` (`status`);

-- Update SellerApplication table
ALTER TABLE `seller_application` 
ADD COLUMN IF NOT EXISTS `store_description` text,
ADD COLUMN IF NOT EXISTS `store_category` varchar(100) NOT NULL DEFAULT 'General',
MODIFY COLUMN `applied_at` timestamp NOT NULL DEFAULT current_timestamp(),
ADD COLUMN IF NOT EXISTS `store_logo` varchar(255) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `store_mission` text DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `return_policy` text DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `return_days` int(11) DEFAULT 7,
ADD COLUMN IF NOT EXISTS `refund_method` varchar(50) DEFAULT 'Original Payment Method',
ADD COLUMN IF NOT EXISTS `business_registration` varchar(255) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `valid_id` varchar(255) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `store_banner` varchar(255) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `followers_count` int(11) DEFAULT 0,
ADD COLUMN IF NOT EXISTS `store_rating` float DEFAULT 5,
ADD COLUMN IF NOT EXISTS `chat_enabled` tinyint(1) DEFAULT 1;

-- Update Order table
ALTER TABLE `order`
MODIFY COLUMN `total_amount` decimal(10,2) NOT NULL,
MODIFY COLUMN `status` varchar(20) DEFAULT 'pending',
MODIFY COLUMN `payment_method` varchar(50) NOT NULL,
MODIFY COLUMN `payment_status` varchar(20) DEFAULT 'pending',
MODIFY COLUMN `shipping_address` text NOT NULL,
MODIFY COLUMN `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
MODIFY COLUMN `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
ADD COLUMN IF NOT EXISTS `stock_deducted` tinyint(1) DEFAULT 0,
ADD COLUMN IF NOT EXISTS `stock_deducted_at` timestamp NULL DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `qr_code` varchar(255) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `tracking_number` varchar(50) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `batch_code` varchar(50) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `label_generated_at` timestamp NULL DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `packed_at` timestamp NULL DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `picked_up_at` timestamp NULL DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `delivered_at` timestamp NULL DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `packed_by` int(11) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `picked_up_by` int(11) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `delivered_by` int(11) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `shipping_notes` text DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `delivery_notes` text DEFAULT NULL;

-- Add foreign key constraints for Order table
ALTER TABLE `order` 
ADD CONSTRAINT IF NOT EXISTS `order_packed_by_fk` FOREIGN KEY (`packed_by`) REFERENCES `user` (`id`),
ADD CONSTRAINT IF NOT EXISTS `order_picked_up_by_fk` FOREIGN KEY (`picked_up_by`) REFERENCES `user` (`id`),
ADD CONSTRAINT IF NOT EXISTS `order_delivered_by_fk` FOREIGN KEY (`delivered_by`) REFERENCES `user` (`id`);

-- Update OrderItem table
ALTER TABLE `order_item`
MODIFY COLUMN `quantity` int(11) NOT NULL,
MODIFY COLUMN `price_at_time` decimal(10,2) NOT NULL;

-- Update Cart table
ALTER TABLE `cart`
MODIFY COLUMN `quantity` int(11) NOT NULL DEFAULT 1,
MODIFY COLUMN `created_at` timestamp NOT NULL DEFAULT current_timestamp();

-- Create missing tables if they don't exist

-- SellerOrderSeen table
CREATE TABLE IF NOT EXISTS `seller_order_seen` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `seller_id` int(11) NOT NULL,
  `order_id` int(11) NOT NULL,
  `seen_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_seller_order_seen_seller` (`seller_id`),
  KEY `idx_seller_order_seen_order` (`order_id`),
  CONSTRAINT `seller_order_seen_seller_fk` FOREIGN KEY (`seller_id`) REFERENCES `user` (`id`),
  CONSTRAINT `seller_order_seen_order_fk` FOREIGN KEY (`order_id`) REFERENCES `order` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ReturnRequest table
CREATE TABLE IF NOT EXISTS `return_request` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `order_id` int(11) NOT NULL,
  `order_item_id` int(11) NOT NULL,
  `buyer_id` int(11) NOT NULL,
  `seller_id` int(11) NOT NULL,
  `reason` text NOT NULL,
  `reason_other` text DEFAULT NULL,
  `description` text DEFAULT NULL,
  `quantity` int(11) DEFAULT 1,
  `images` json DEFAULT NULL,
  `video_filename` varchar(255) DEFAULT NULL,
  `request_type` varchar(20) NOT NULL,
  `status` varchar(30) DEFAULT 'submitted',
  `created_at` datetime DEFAULT current_timestamp(),
  `processed_at` datetime DEFAULT NULL,
  `processed_by` int(11) DEFAULT NULL,
  `refund_amount` decimal(10,2) DEFAULT NULL,
  `admin_notes` text DEFAULT NULL,
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `seller_response_reason` text DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `return_request_order_fk` (`order_id`),
  KEY `return_request_order_item_fk` (`order_item_id`),
  KEY `return_request_buyer_fk` (`buyer_id`),
  KEY `return_request_seller_fk` (`seller_id`),
  CONSTRAINT `return_request_order_fk` FOREIGN KEY (`order_id`) REFERENCES `order` (`id`),
  CONSTRAINT `return_request_order_item_fk` FOREIGN KEY (`order_item_id`) REFERENCES `order_item` (`id`),
  CONSTRAINT `return_request_buyer_fk` FOREIGN KEY (`buyer_id`) REFERENCES `user` (`id`),
  CONSTRAINT `return_request_seller_fk` FOREIGN KEY (`seller_id`) REFERENCES `user` (`id`),
  CONSTRAINT `return_request_processed_by_fk` FOREIGN KEY (`processed_by`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- RestockRequest table
CREATE TABLE IF NOT EXISTS `restock_request` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `product_id` int(11) NOT NULL,
  `seller_id` int(11) NOT NULL,
  `requested_quantity` int(11) NOT NULL,
  `status` varchar(20) DEFAULT 'pending',
  `created_at` datetime DEFAULT current_timestamp(),
  `processed_at` datetime DEFAULT NULL,
  `processed_by` int(11) DEFAULT NULL,
  `admin_notes` text DEFAULT NULL,
  `approved_quantity` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `restock_request_product_fk` (`product_id`),
  KEY `restock_request_seller_fk` (`seller_id`),
  KEY `restock_request_processed_by_fk` (`processed_by`),
  CONSTRAINT `restock_request_product_fk` FOREIGN KEY (`product_id`) REFERENCES `product` (`id`),
  CONSTRAINT `restock_request_seller_fk` FOREIGN KEY (`seller_id`) REFERENCES `user` (`id`),
  CONSTRAINT `restock_request_processed_by_fk` FOREIGN KEY (`processed_by`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ReturnPickup table
CREATE TABLE IF NOT EXISTS `return_pickup` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `return_request_id` int(11) NOT NULL,
  `rider_id` int(11) DEFAULT NULL,
  `status` varchar(30) DEFAULT 'available',
  `buyer_address` text DEFAULT NULL,
  `seller_address` text DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `picked_up_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `return_pickup_return_request_fk` (`return_request_id`),
  KEY `return_pickup_rider_fk` (`rider_id`),
  CONSTRAINT `return_pickup_return_request_fk` FOREIGN KEY (`return_request_id`) REFERENCES `return_request` (`id`),
  CONSTRAINT `return_pickup_rider_fk` FOREIGN KEY (`rider_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- WalletTransaction table
CREATE TABLE IF NOT EXISTS `wallet_transaction` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `order_id` int(11) DEFAULT NULL,
  `amount` decimal(10,2) NOT NULL,
  `type` varchar(20) DEFAULT 'credit',
  `source` varchar(50) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `wallet_transaction_user_fk` (`user_id`),
  KEY `wallet_transaction_order_fk` (`order_id`),
  CONSTRAINT `wallet_transaction_user_fk` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`),
  CONSTRAINT `wallet_transaction_order_fk` FOREIGN KEY (`order_id`) REFERENCES `order` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- RiderChatMessage table
CREATE TABLE IF NOT EXISTS `rider_chat_message` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `buyer_id` int(11) NOT NULL,
  `rider_id` int(11) NOT NULL,
  `order_id` int(11) DEFAULT NULL,
  `message` text NOT NULL,
  `sender_role` varchar(10) NOT NULL,
  `is_read` tinyint(1) DEFAULT 0,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `rider_chat_buyer_fk` (`buyer_id`),
  KEY `rider_chat_rider_fk` (`rider_id`),
  KEY `rider_chat_order_fk` (`order_id`),
  CONSTRAINT `rider_chat_buyer_fk` FOREIGN KEY (`buyer_id`) REFERENCES `user` (`id`),
  CONSTRAINT `rider_chat_rider_fk` FOREIGN KEY (`rider_id`) REFERENCES `user` (`id`),
  CONSTRAINT `rider_chat_order_fk` FOREIGN KEY (`order_id`) REFERENCES `order` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Coupon table
CREATE TABLE IF NOT EXISTS `coupon` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `code` varchar(50) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `discount_type` varchar(20) DEFAULT 'percent',
  `discount_value` decimal(10,2) NOT NULL,
  `min_order_amount` decimal(10,2) DEFAULT 0.00,
  `max_uses` int(11) DEFAULT NULL,
  `used_count` int(11) DEFAULT 0,
  `valid_from` datetime DEFAULT NULL,
  `valid_until` datetime DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT 1,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `coupon_code_unique` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- RiderApplication table
CREATE TABLE IF NOT EXISTS `rider_application` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `vehicle_type` varchar(50) NOT NULL,
  `vehicle_number` varchar(20) NOT NULL,
  `employee_id` varchar(50) DEFAULT NULL,
  `status` varchar(20) DEFAULT 'pending',
  `applied_at` datetime DEFAULT current_timestamp(),
  `reviewed_at` datetime DEFAULT NULL,
  `reviewed_by` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `rider_application_user_fk` (`user_id`),
  KEY `rider_application_reviewed_by_fk` (`reviewed_by`),
  CONSTRAINT `rider_application_user_fk` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`),
  CONSTRAINT `rider_application_reviewed_by_fk` FOREIGN KEY (`reviewed_by`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Update Product table
ALTER TABLE `product`
MODIFY COLUMN `name` varchar(120) NOT NULL,
MODIFY COLUMN `description` text NOT NULL,
MODIFY COLUMN `price` decimal(10,2) NOT NULL,
MODIFY COLUMN `stock` int(11) NOT NULL DEFAULT 0,
MODIFY COLUMN `status` varchar(20) DEFAULT 'active',
MODIFY COLUMN `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
ADD COLUMN IF NOT EXISTS `video_filename` varchar(255) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `gallery` json DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `subcategory_id` int(11) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `is_deleted` tinyint(1) DEFAULT 0,
ADD COLUMN IF NOT EXISTS `rejection_reason` text DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `featured` tinyint(1) DEFAULT 0,
ADD COLUMN IF NOT EXISTS `show_in_new_arrival` tinyint(1) NOT NULL DEFAULT 0;

-- Add foreign key for product subcategory
ALTER TABLE `product` 
ADD CONSTRAINT IF NOT EXISTS `product_subcategory_fk` FOREIGN KEY (`subcategory_id`) REFERENCES `subcategory` (`id`);

-- Update Review table
ALTER TABLE `review`
MODIFY COLUMN `rating` int(11) NOT NULL,
MODIFY COLUMN `created_at` datetime DEFAULT current_timestamp(),
MODIFY COLUMN `status` varchar(20) DEFAULT 'published',
ADD COLUMN IF NOT EXISTS `media` json DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `verified_purchase` tinyint(1) DEFAULT 0,
ADD COLUMN IF NOT EXISTS `order_id` int(11) DEFAULT NULL;

-- Add foreign key for review order
ALTER TABLE `review` 
ADD CONSTRAINT IF NOT EXISTS `review_order_fk` FOREIGN KEY (`order_id`) REFERENCES `order` (`id`);

-- Update Notification table
ALTER TABLE `notification`
MODIFY COLUMN `created_at` datetime DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `image_url` varchar(255) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `link` varchar(255) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `type` varchar(40) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `actor_user_id` int(11) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `order_id` int(11) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `images` json DEFAULT NULL;

-- Add foreign keys for notification
ALTER TABLE `notification` 
ADD CONSTRAINT IF NOT EXISTS `notification_actor_fk` FOREIGN KEY (`actor_user_id`) REFERENCES `user` (`id`);

-- Update Address table
ALTER TABLE `address`
MODIFY COLUMN `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
ADD COLUMN IF NOT EXISTS `latitude` double DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `longitude` double DEFAULT NULL;

-- Update Category table
ALTER TABLE `category`
MODIFY COLUMN `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
ADD COLUMN IF NOT EXISTS `cover_image_filename` varchar(255) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `status` varchar(20) DEFAULT 'active';

-- Update Subcategory table
ALTER TABLE `subcategory`
MODIFY COLUMN `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
ADD COLUMN IF NOT EXISTS `status` varchar(20) DEFAULT 'active';

-- Update HeroSlide table
ALTER TABLE `hero_slide`
MODIFY COLUMN `created_at` datetime DEFAULT current_timestamp(),
MODIFY COLUMN `is_active` tinyint(1) DEFAULT 1;

-- Update ThemeSetting table
ALTER TABLE `theme_setting`
MODIFY COLUMN `slide_duration` float DEFAULT 6,
MODIFY COLUMN `transition_duration` float DEFAULT 0.8;

-- Update DeliveryPersonnel table
ALTER TABLE `delivery_personnel`
MODIFY COLUMN `created_at` datetime DEFAULT NULL,
MODIFY COLUMN `updated_at` datetime DEFAULT NULL ON UPDATE current_timestamp(),
MODIFY COLUMN `status` varchar(20) DEFAULT NULL;

-- Update QRScanLog table
ALTER TABLE `qr_scan_log`
MODIFY COLUMN `created_at` datetime DEFAULT NULL;

-- Update OrderLabel table
ALTER TABLE `order_label`
MODIFY COLUMN `created_at` datetime DEFAULT NULL,
MODIFY COLUMN `updated_at` datetime DEFAULT NULL ON UPDATE current_timestamp(),
ADD COLUMN IF NOT EXISTS `returned_by` int(11) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `return_notes` text DEFAULT NULL;

-- Add foreign key for order_label returned_by
ALTER TABLE `order_label` 
ADD CONSTRAINT IF NOT EXISTS `order_label_returned_by_fk` FOREIGN KEY (`returned_by`) REFERENCES `user` (`id`);

-- Update StoreChatMessage table
ALTER TABLE `store_chat_message`
MODIFY COLUMN `created_at` datetime DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `is_read` tinyint(1) DEFAULT NULL;

-- Drop and recreate Flask Dance OAuth table if needed
DROP TABLE IF EXISTS `flask_dance_oauth`;

-- Update OAuth table
ALTER TABLE `oauth`
MODIFY COLUMN `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
ADD COLUMN IF NOT EXISTS `provider_user_id` varchar(256) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS `provider` varchar(50) DEFAULT NULL;

-- Fix OAuth table structure
ALTER TABLE `oauth` 
MODIFY COLUMN `provider_user_id` varchar(256) NOT NULL,
MODIFY COLUMN `provider` varchar(50) NOT NULL,
DROP INDEX IF EXISTS `provider_user_id`,
ADD UNIQUE KEY `provider_user_id` (`provider_user_id`);

-- Re-enable foreign key checks
SET FOREIGN_KEY_CHECKS = 1;

-- Insert missing default data

-- Insert default theme setting if not exists
INSERT IGNORE INTO `theme_setting` (`id`, `logo_filename`, `site_name`, `primary_color`, `secondary_color`, `footer_color`, `slide_duration`, `transition_duration`) 
VALUES (1, 'logo_ulit.png', 'Kids & Baby Store', '#1a2842', '#000000', '#1a2842', 6, 0.8);

-- Insert default admin user if not exists
INSERT IGNORE INTO `user` (`id`, `username`, `first_name`, `last_name`, `email`, `password`, `phone`, `address`, `role`, `status`, `email_verified`, `verification_code`, `valid_id`, `created_at`, `two_factor_enabled`, `email_notifications`) 
VALUES (1, 'admin', 'Admin', 'User', 'admin@kidscommerce.com', 'admin123', '09123456789', 'Admin Office, Manila', 'admin', 'active', 0, NULL, NULL, NOW(), 0, 1);

-- Insert admin profile if not exists
INSERT IGNORE INTO `admin_profile` (`id`, `user_id`, `full_name`, `contact_number`, `system_role`, `last_login`, `account_status`, `two_factor_enabled`, `password_reset_required`, `created_at`, `updated_at`) 
VALUES (1, 1, 'Admin User', '09123456789', 'Administrator', NULL, 'Active', 0, 0, NOW(), NOW());

-- Update existing users to have usernames if missing
UPDATE `user` SET `username` = CONCAT('user', `id`) WHERE `username` = 'user' OR `username` IS NULL;

-- Update existing products to have proper defaults
UPDATE `product` SET `featured` = 0 WHERE `featured` IS NULL;
UPDATE `product` SET `show_in_new_arrival` = 0 WHERE `show_in_new_arrival` IS NULL;
UPDATE `product` SET `is_deleted` = 0 WHERE `is_deleted` IS NULL;

-- Update existing addresses to have proper defaults
UPDATE `address` SET `latitude` = NULL WHERE `latitude` IS NULL;
UPDATE `address` SET `longitude` = NULL WHERE `longitude` IS NULL;

-- Update existing notifications to have proper defaults
UPDATE `notification` SET `is_read` = 0 WHERE `is_read` IS NULL;

-- Update existing store chat messages to have proper defaults
UPDATE `store_chat_message` SET `is_read` = 0 WHERE `is_read` IS NULL;

-- Update existing reviews to have proper defaults
UPDATE `review` SET `verified_purchase` = 0 WHERE `verified_purchase` IS NULL;

-- Commit the changes
COMMIT;
