UPDATE dropdown_master
SET is_active = TRUE,
    display_order = 5,
    updated_at = now()
WHERE category = 'CONTRACT_TYPE'
  AND lower(value) = 'sow';

INSERT INTO dropdown_master (category, value, display_order, is_active)
SELECT 'CONTRACT_TYPE', 'SOW', 5, TRUE
WHERE NOT EXISTS (
    SELECT 1
    FROM dropdown_master
    WHERE category = 'CONTRACT_TYPE'
      AND lower(value) = 'sow'
);
