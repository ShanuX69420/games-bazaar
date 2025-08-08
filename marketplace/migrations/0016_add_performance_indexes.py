# Generated migration for adding performance indexes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0015_reviewreply'),
    ]

    operations = [
        # Add indexes to Product model for frequently queried fields
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_product_created_at_idx ON marketplace_product (created_at);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_product_created_at_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_product_is_active_idx ON marketplace_product (is_active);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_product_is_active_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_product_price_idx ON marketplace_product (price);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_product_price_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_product_automatic_delivery_idx ON marketplace_product (automatic_delivery);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_product_automatic_delivery_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_product_seller_game_idx ON marketplace_product (seller_id, game_id);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_product_seller_game_idx;"
        ),
        
        # Add indexes to Order model
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_order_status_idx ON marketplace_order (status);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_order_status_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_order_created_at_idx ON marketplace_order (created_at);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_order_created_at_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_order_updated_at_idx ON marketplace_order (updated_at);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_order_updated_at_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_order_buyer_status_idx ON marketplace_order (buyer_id, status);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_order_buyer_status_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_order_seller_status_idx ON marketplace_order (seller_id, status);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_order_seller_status_idx;"
        ),
        
        # Add indexes to Review model
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_review_created_at_idx ON marketplace_review (created_at);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_review_created_at_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_review_seller_rating_idx ON marketplace_review (seller_id, rating);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_review_seller_rating_idx;"
        ),
        
        # Add indexes to Message model
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_message_timestamp_idx ON marketplace_message (timestamp);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_message_timestamp_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_message_conversation_timestamp_idx ON marketplace_message (conversation_id, timestamp);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_message_conversation_timestamp_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_message_is_read_idx ON marketplace_message (is_read);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_message_is_read_idx;"
        ),
        
        # Add indexes to Profile model
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_profile_last_seen_idx ON marketplace_profile (last_seen);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_profile_last_seen_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_profile_show_listings_idx ON marketplace_profile (show_listings_on_site);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_profile_show_listings_idx;"
        ),
        
        # Add indexes to Transaction model
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_transaction_created_at_idx ON marketplace_transaction (created_at);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_transaction_created_at_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_transaction_user_type_idx ON marketplace_transaction (user_id, transaction_type);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_transaction_user_type_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_transaction_status_idx ON marketplace_transaction (status);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_transaction_status_idx;"
        ),
        
        # Add indexes to Game model
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_game_title_idx ON marketplace_game (title);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_game_title_idx;"
        ),
        
        # Add indexes to UserGameBoost model
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_usergameboost_boosted_at_idx ON marketplace_usergameboost (boosted_at);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_usergameboost_boosted_at_idx;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS marketplace_usergameboost_user_game_idx ON marketplace_usergameboost (user_id, game_id);",
            reverse_sql="DROP INDEX IF EXISTS marketplace_usergameboost_user_game_idx;"
        ),
    ]