-- 005_grade_classes_and_planner_constraints.sql

CREATE TABLE IF NOT EXISTS grade_classes (
    id SERIAL PRIMARY KEY,
    name_en VARCHAR(100) NOT NULL UNIQUE,
    name_ar VARCHAR(100) NOT NULL UNIQUE,
    "order" INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

ALTER TABLE shift_locations
    ADD CONSTRAINT uq_shift_location_day_shift_location
    UNIQUE (day_plan_id, shift_id, location_id);

ALTER TABLE assignments
    ADD CONSTRAINT uq_assignment_shift_location_slot
    UNIQUE (shift_location_id, slot_index);
