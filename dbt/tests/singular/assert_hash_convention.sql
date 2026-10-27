-- The hash key convention (ADR-005) on fixed inputs, checked against values computed outside
-- the warehouse (Python hashlib): SHA-256 over upper-cased, trimmed parts joined by "||".
-- Identical results on DuckDB and Fabric are what makes local and cloud keys interchangeable.
with cases as (
    select
        {{ bw_hash_key(["'CIK'", "'320193'"]) }} as actual,
        'fda77dc91be7ee9505b2ce380e66b5ac5c6cce83e012a340f1aedf70d6ebe473' as expected
    union all
    select
        {{ bw_hash_key(["' cik '", "' 320193'"]) }},
        'fda77dc91be7ee9505b2ce380e66b5ac5c6cce83e012a340f1aedf70d6ebe473'
    union all
    select
        {{ bw_hash_key(["'0000320193-24-000123'"]) }},
        'abbc5d6e6b3b0685889ba168f2573d7e6f2ab00d0d0d21b9737e582465920bca'
    union all
    select
        {{ bw_hash_key(["'0000320193-24-000123'", "'CIK'", "'320193'"]) }},
        'e7dbbf8dcb8958ee53e84cc8f55aef1d2bb72b510d13ce23a012789d19a455d5'
)

select * from cases where actual <> expected
