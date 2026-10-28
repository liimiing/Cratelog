-- Existing installations only: run ONCE before deploying the new PHP files.
-- Retains all existing album IDs, ratings, tracks and revisions.
ALTER TABLE cratelog_albums
 MODIFY COLUMN rating DECIMAL(2,1) UNSIGNED NOT NULL DEFAULT 0,
 ADD COLUMN personal_comment TEXT NULL,
 ADD COLUMN documents JSON NULL;
