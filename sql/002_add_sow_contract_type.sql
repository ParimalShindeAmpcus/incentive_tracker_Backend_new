-- Add SOW to the contract type master for existing databases.
INSERT INTO dropdown_master (category, value, display_order)
SELECT 'CONTRACT_TYPE', 'SOW', 5
WHERE NOT EXISTS (
    SELECT 1
    FROM dropdown_master
    WHERE category = 'CONTRACT_TYPE'
      AND value = 'SOW'
      AND organization_id IS NULL
);