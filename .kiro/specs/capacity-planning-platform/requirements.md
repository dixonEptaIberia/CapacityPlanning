# Requirements Document

## Introduction

This document specifies the requirements for a capacity planning platform that replaces the spreadsheet-based assembly-line capacity planning currently used across several European plants (Limana, Solesino, Casale, Istanbul, France, and Bradford). The platform preserves the existing business logic while improving scenario management, information sharing, reporting, version control, governance, and data transfer to the existing planning software.

The application is a React + TypeScript frontend, a Python backend, and AWS cloud integration. It presents a spreadsheet-like layout so current users can adopt it without learning an entirely new structure. It manages **cadence and capacity** — it does **not** create planned orders or replace the existing SAP interfaces, which remain the responsibility of the existing planning tool (Compass).

### Scope boundaries

- **In scope:** cadence/capacity/workforce planning, scenarios, versioning, notes, plant and regional views, reporting/export, master-data import, governance, and configuration.
- **Out of scope:** planned-order generation and the SAP export (owned by Compass), and any change to Compass's five-year-old planned-order rules.

### Glossary

- **Cadence:** the approved rate/worker combination for a line that yields a theoretical weekly output.
- **Capacity delta / adjustment:** a manual change to a line's output when it is delayed, ahead, or needs additional capacity.
- **Frozen period:** the near-term weeks that cannot be changed; length varies by plant and industrial cycle.
- **Official version:** the capacity balance released by central planning and treated as the agreement between central planning and the factories.
- **Compass:** the existing planning tool that generates planned orders and exports to SAP.
- **Click Sense:** the analytics/reporting tool (Qlik Sense) consuming structured tables from the platform.

## Requirements

### Requirement 1: Spreadsheet-like Capacity Planning Grid

**User Story:** As a planner, I want a familiar spreadsheet-like grid of plants, product lines, and weekly columns, so that I can plan capacity without learning a new structure.

#### Acceptance Criteria

1. WHEN a planner opens a plant view THEN the system SHALL display product lines as rows and weeks as columns, matching the current spreadsheet layout.
2. THE system SHALL display, per product line, the product/project name, product family, and production-scheduler information identifying the relevant production routings and SAP work centers.
3. THE system SHALL display, per weekly cell, the working days, worker cadence, expected pieces, and capacity adjustment.
4. WHEN a planner edits an editable weekly cell THEN the system SHALL persist the change to the central dataset.
5. WHILE a week is within a plant's frozen period THE system SHALL prevent edits to that week's planning values.

### Requirement 2: Theoretical Output and Worker Cadence

**User Story:** As a planner, I want theoretical weekly output calculated from cadence and workers, so that expected pieces are consistent and I only use approved staffing structures.

#### Acceptance Criteria

1. WHEN a cadence and worker configuration are assigned to a line THEN the system SHALL calculate the theoretical weekly output from that configuration (e.g., a one-worker configuration yields 60 pieces; an "11 + 11" two-shift configuration of 11 workers per shift yields 144 pieces).
2. THE system SHALL only allow cadence and worker combinations approved by the technical department, and SHALL NOT allow the planner to invent alternative staffing structures.
3. WHEN a line is delayed, ahead of schedule, or needs additional capacity THEN the system SHALL allow the planner to record a capacity adjustment to the actual output.
4. THE system SHALL derive expected pieces from the approved cadence, while allowing the recorded capacity adjustment to override the theoretical value.

### Requirement 3: Workforce Target and Availability

**User Story:** As a planner, I want to define target staffing and see whether available workers are above or below target, so that I respect the total number of available workers.

#### Acceptance Criteria

1. THE system SHALL allow a planner to define target staffing per plant (or planning area).
2. WHEN staffing assigned across lines changes THEN the system SHALL indicate whether the available workforce is above, at, or below the agreed target.
3. WHEN a planner increases staffing on one line and the plant manager is not hiring additional workers THEN the system SHALL make the resulting shortfall against target visible so staffing can be reduced elsewhere.

### Requirement 4: Combined and Linked Lines (Special Production Rules)

**User Story:** As a planner, I want linked lines to adjust together, so that lines that appear separate but operate as one combined process stay consistent.

#### Acceptance Criteria

1. WHEN two lines are configured as one combined process THEN the system SHALL treat a cadence change on one line as automatically reducing or adjusting the output of the related line.
2. THE system SHALL support special production rules and nonstandard cases beyond the standard cadence calculation.
3. WHERE a special rule applies THE system SHALL apply it consistently across all affected weekly cells.

### Requirement 5: Scenario Management

**User Story:** As a planner, I want to model alternative demand or capacity assumptions within the platform, so that I avoid proliferating copies of the official spreadsheet.

#### Acceptance Criteria

1. WHEN a planner explores an alternative demand or capacity assumption THEN the system SHALL allow a scenario to be created without copying the official dataset into a separate file.
2. THE system SHALL distinguish scenarios (hypotheses) from the official capacity balance.
3. WHEN a scenario is agreed with a facility THEN the system SHALL allow it to be promoted toward an official version without manual re-entry.

### Requirement 6: Formal Planning Cycle and Frozen Periods

**User Story:** As central planning, I want to release an official capacity balance and control when it changes, so that the platform remains the agreement between central planning and the factories.

#### Acceptance Criteria

1. WHEN central planning releases the approved capacity balance THEN the system SHALL mark it as the official version and make it available to relevant stakeholders.
2. THE system SHALL allow the balance to be changed on a defined cadence (once per week via the dedicated meeting) rather than continuously.
3. THE system SHALL support a configurable frozen period per plant (for example approximately three weeks on average; "1 + 2" weeks for some plants, one additional week for Bradford, six weeks for Casale).
4. WHEN the current week ends THEN the system SHALL require the first week outside the frozen period to be finalized by the Friday of the current week, while leaving later weeks open for subsequent discussion.

### Requirement 7: Version Control and Historical Access

**User Story:** As a planner, I want named versions and history, so that I can compare against the last official version and recover previous states.

#### Acceptance Criteria

1. WHEN a planner saves a version THEN the system SHALL store it with plant, time, and explanatory information.
2. WHEN a planner requests a comparison THEN the system SHALL show changes relative to the last official version.
3. THE system SHALL distinguish changes already applied in the planning software from proposals that remain hypotheses.
4. WHEN a planner opens historical access THEN the system SHALL make closed or previously hidden weeks visible for review.
5. THE system SHALL provide a separate summary area that shows saved official versions without allowing users to modify the main planning data.

### Requirement 8: Plant, Multi-Plant, and Regional Views

**User Story:** As a regional planner, I want to view one plant, multiple plants, or all EMEA facilities together, so that I can coordinate overlapping production capabilities.

#### Acceptance Criteria

1. THE system SHALL display a single facility, multiple facilities, or broader regional combinations from one central dataset.
2. WHERE products overlap across plants (for example platforms A1, Alpha 1, and NC5) THE system SHALL evaluate total potential output across facilities rather than treating each facility in isolation.
3. WHEN production is considered for transfer between plants for a market or country THEN the system SHALL support recording the intended change while indicating that sales must be consulted and the change agreed before it is applied.

### Requirement 9: Planning Notes

**User Story:** As a planner, I want to attach notes to planning areas, so that the context behind a decision is preserved.

#### Acceptance Criteria

1. WHEN a planner records an operational event (such as a strike) THEN the system SHALL store the note in the relevant planning area.
2. WHERE a note exists THE system SHALL highlight the cell or area to indicate its presence.
3. WHEN a planner opens a highlighted area THEN the system SHALL display the stored note and its context.

### Requirement 10: Reporting and Export

**User Story:** As a planner, I want structured reporting and exports, so that I reduce manual copying and data-entry mistakes.

#### Acceptance Criteria

1. THE system SHALL produce structured tables suitable for Click Sense (Qlik Sense) analysis.
2. THE system SHALL produce a spreadsheet suitable for import into Compass, containing the approved cadence updates.
3. WHEN a planner exports approved cadence updates THEN the system SHALL avoid requiring the planner to copy cadence week by week into the planning software manually.

### Requirement 11: Master-Data Import

**User Story:** As a planner, I want to import technical master data from Excel, so that unstable or changing values can be updated without changing application code.

#### Acceptance Criteria

1. THE system SHALL import technical values such as pieces, time values, and line data from an Excel spreadsheet.
2. WHEN master data changes THEN the system SHALL allow re-import without modifying application code.
3. IF an imported file fails validation THEN the system SHALL reject the import and report the errors without corrupting existing data.

### Requirement 12: Access Control and Governance

**User Story:** As an administrator, I want role-based access and one central dataset, so that official numbers are consistent and protected.

#### Acceptance Criteria

1. THE system SHALL grant full maintenance rights only to a limited central-planning group.
2. THE system SHALL allow other stakeholders to view official information without changing settings.
3. THE system SHALL use one centrally managed dataset rather than files stored on individual laptops.
4. THE system SHALL allow plant users to access official versions and historical information without granting edit access to the main planning view.
5. WHILE a user lacks edit rights THE system SHALL prevent that user from modifying planning data or configuration.

### Requirement 13: Configuration over Code

**User Story:** As an authorized internal user, I want to configure the platform through a controlled layer, so that ordinary business changes do not require editing the code base.

#### Acceptance Criteria

1. THE system SHALL allow authorized users to add, switch, or remove production lines through a configuration or database layer.
2. THE system SHALL allow authorized users to maintain master data and define special rules through configuration.
3. THE system SHALL allow authorized users to add dashboard fields or KPIs through configuration.
4. THE system SHALL NOT require direct access to the full code base for ordinary business changes.

### Requirement 14: Multi-Language Support

**User Story:** As a user in a multi-country organization, I want the interface in my language, so that I can work effectively.

#### Acceptance Criteria

1. THE system SHALL provide English as the company language.
2. THE system SHALL provide Italian.
3. WHERE technically feasible THE system SHALL provide French and Turkish.
4. WHEN a user selects a supported language THEN the system SHALL display the interface in that language.

### Requirement 15: Adaptability for Future Growth

**User Story:** As the business, I want the platform to adapt as new plants, lines, companies, or requirements emerge, so that a small number of authorized internal users can maintain it safely over time.

#### Acceptance Criteria

1. WHEN a new plant, production line, or company is introduced THEN the system SHALL allow it to be added through configuration by authorized users.
2. THE system SHALL allow a hypothetical new facility or production line to be added for testing without affecting official data.
3. THE system SHALL constrain configuration and rule maintenance to a small number of authorized internal users.
