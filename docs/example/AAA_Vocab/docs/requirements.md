# IELTS Vocabulary Learning System Requirements

## 1. Overview

**Purpose**: Define detailed technical requirements for an IELTS vocabulary learning system that transforms passive vocabulary recognition into active production capability through structured learning, scientific review scheduling, and multi-modal assessment.

**Scope**: This document specifies the data structures, algorithms, persistence mechanisms, and functional requirements needed to implement the agent described in `agent_specification.md`.

**Target Audience**: System implementers, maintainers, and integration developers.

---

## 2. Core Functional Requirements

### 2.1 Vocabulary Library Management

**FR-VL-001**: The system MUST support loading vocabulary entries in the format defined by `vocab_format.md`.

**FR-VL-002**: Each vocabulary entry MUST be parsed to extract:
- Pronunciation data (British/American IPA, stress patterns, listening traps)
- Dictionary-based definitions with source attribution (Oxford, Cambridge, Collins)
- Word families and derivatives
- High-frequency collocations with example sentences
- Confusion matrices comparing near-synonyms
- Active output drills (gap-fill, speaking scenarios, writing scenarios)

**FR-VL-003**: The system MUST assign a unique identifier (`word_id`) to each vocabulary entry.

**FR-VL-004**: The system MUST maintain an index of all vocabulary entries for efficient lookup and retrieval.

### 2.2 Learning Record Management

**FR-LR-001**: For each vocabulary entry, the system MUST maintain a persistent learning record.

**FR-LR-002**: Each learning record MUST track:
- `word_id`: unique identifier linking to vocabulary entry
- `first_encounter`: timestamp of initial learning session
- `last_review`: timestamp of most recent review
- `next_review`: calculated timestamp for next scheduled review
- `review_count`: total number of reviews completed
- `error_count`: cumulative count of incorrect responses
- `consecutive_correct`: count of consecutive correct responses (reset on error)
- `mastery_level`: integer 0-5 indicating proficiency level
- `assessment_history`: chronological list of all assessment attempts

**FR-LR-003**: Assessment history entries MUST include:
- `timestamp`: when the assessment occurred
- `question_type`: one of `["mcq", "short_answer", "fill_blank"]`
- `question_content`: the actual question presented
- `user_response`: the user's answer
- `correct_answer`: the expected answer
- `correct`: boolean indicating correctness
- `time_spent`: response time in seconds

**FR-LR-004**: Learning records MUST persist across application sessions.

**FR-LR-005**: The system MUST provide functions to:
- Initialize a new learning record when a word is first encountered
- Update a learning record after each assessment
- Retrieve learning records by `word_id`
- Query learning records by criteria (e.g., due for review, high error rate)

### 2.3 Scientific Review Scheduling

**FR-RS-001**: The system MUST implement a spaced repetition algorithm to calculate optimal review intervals.

**FR-RS-002**: Review intervals MUST be calculated based on:
- Time elapsed since first encounter
- Number of correct vs. incorrect attempts
- Consecutive correct response count
- Current mastery level

**FR-RS-003**: The system MUST maintain a priority queue of vocabulary items due for review.

**FR-RS-004**: The review queue MUST prioritize items by:
1. Overdue status (past `next_review` timestamp)
2. Error rate (items with higher error rates prioritized)
3. Least recently reviewed (longer time since `last_review`)

**FR-RS-005**: The system MUST support manual override to force immediate review of specific words.

**FR-RS-006**: The system MUST recalculate `next_review` timestamps after each assessment attempt.

### 2.4 Multi-Modal Assessment Generation

**FR-AG-001**: The system MUST generate three types of assessments:
- Multiple Choice Questions (MCQ)
- Short Answer Questions
- Fill-in-the-Blank Exercises

#### 2.4.1 Multiple Choice Questions

**FR-AG-MCQ-001**: MCQ MUST test:
- Understanding of word definitions
- Appropriate collocation usage
- Synonym/antonym distinctions
- Contextual appropriateness

**FR-AG-MCQ-002**: Each MCQ MUST have:
- One correct answer
- 3-4 distractor options generated from:
  - Words in the confusion matrix
  - Previously learned vocabulary with similar meanings
  - Common semantic neighbors

**FR-AG-MCQ-003**: MCQ format MUST be:
```
Question: [Context sentence or definition prompt]
A) [Option 1]
B) [Option 2]
C) [Option 3]
D) [Option 4]
```

#### 2.4.2 Short Answer Questions

**FR-AG-SA-001**: Short answer questions MUST test:
- Definition recall (English → Chinese or Chinese → English)
- Collocation completion
- Explanation of nuance differences between near-synonyms
- Appropriate context usage

**FR-AG-SA-002**: Short answer questions MUST provide:
- Clear prompt indicating expected response format
- Chinese translation hints when appropriate
- Evaluation criteria for correctness

#### 2.4.3 Fill-in-the-Blank Exercises

**FR-AG-FB-001**: Fill-in-blank exercises MUST:
- Present a sentence-level context with one blank
- Clearly indicate whether the blank expects `[WORD]` (single word) or `[PHRASE]` (multi-word expression)
- Only use vocabulary from items the user has previously learned (requires tracking)
- Provide Chinese translation of the sentence as a hint

**FR-AG-FB-002**: Fill-in-blank format MUST be:
```
[English sentence with ________ blank]
[中文翻译提示]
Type: [WORD] or [PHRASE]
```

**FR-AG-FB-003**: The system MUST validate that all vocabulary used in fill-in-blank exercises has been previously encountered by the user.

### 2.5 Progress Analytics

**FR-PA-001**: The system MUST provide analytics on:
- Total vocabulary count
- Mastered vocabulary count (mastery_level >= 4)
- In-review vocabulary count (0 < mastery_level < 4)
- Due-for-review count
- Error rate distribution
- Learning streak (consecutive days with reviews)
- Estimated time to mastery for in-progress words

**FR-PA-002**: The system MUST generate visualizations of:
- Progress over time (words mastered per week/month)
- Error patterns (words frequently confused)
- Review compliance (scheduled vs. actual reviews)
- Mastery level distribution

---

## 3. Spaced Repetition Algorithm Specification

### 3.1 Algorithm Overview

The system uses an adaptive spaced repetition algorithm based on the SuperMemo SM-2 algorithm with modifications for error tracking.

### 3.2 Initial Learning Phase

**SR-INIT-001**: When a word is first encountered:
- `first_encounter` = current timestamp
- `last_review` = current timestamp
- `next_review` = `first_encounter` + 1 day
- `review_count` = 0
- `error_count` = 0
- `consecutive_correct` = 0
- `mastery_level` = 0

### 3.3 Review Interval Calculation

**SR-CALC-001**: After each assessment, calculate the next review interval based on performance:

```
if response is CORRECT:
    consecutive_correct += 1
    
    if consecutive_correct == 1:
        interval = 1 day
    elif consecutive_correct == 2:
        interval = 3 days
    elif consecutive_correct == 3:
        interval = 7 days
    elif consecutive_correct == 4:
        interval = 14 days
    elif consecutive_correct == 5:
        interval = 30 days
    else:
        interval = previous_interval * 2 (max 180 days)
    
    mastery_level = min(5, consecutive_correct)

if response is INCORRECT:
    consecutive_correct = 0
    error_count += 1
    
    if error_count == 1:
        interval = 0.5 day (12 hours)
    elif error_count == 2:
        interval = 1 day
    else:
        interval = 2 days
    
    mastery_level = max(0, mastery_level - 1)

next_review = current_timestamp + interval
last_review = current_timestamp
review_count += 1
```

**SR-CALC-002**: Mastery level transitions:
- Level 0: Not yet mastered, high error rate
- Level 1: Basic recognition (1 consecutive correct)
- Level 2: Developing familiarity (2 consecutive correct)
- Level 3: Good retention (3 consecutive correct)
- Level 4: Strong retention (4 consecutive correct)
- Level 5: Mastered (5+ consecutive correct)

**SR-CALC-003**: Words with `mastery_level >= 4` are considered "mastered" but continue to appear in reviews at longer intervals to prevent forgetting.

### 3.4 Overdue Handling

**SR-OVERDUE-001**: If a word is overdue (current time > `next_review`), calculate overdue penalty:

```
overdue_days = (current_time - next_review) / 1 day
penalty_factor = min(2.0, 1.0 + (overdue_days / 7))

# On next correct response, reduce interval by penalty factor
adjusted_interval = base_interval / penalty_factor
```

### 3.5 Review Session Limits

**SR-LIMIT-001**: To prevent cognitive overload:
- Maximum 20 new words per day
- Maximum 50 review items per session
- Minimum 10 minutes recommended between sessions

---

## 4. Data Persistence Specifications

### 4.1 Storage Location

**DP-LOC-001**: All learning data MUST be stored in `.memoria/learning_records/` directory.

**DP-LOC-002**: Directory structure:
```
.memoria/
  learning_records/
    {word_id}.yaml          # Individual learning records
    progress_summary.json   # Aggregate statistics
    backup/                 # Automatic backups
      {timestamp}/
        {word_id}.yaml
        progress_summary.json
```

### 4.2 Learning Record File Format

**DP-FORMAT-001**: Each learning record MUST be stored as a YAML file with the following structure:

```yaml
word_id: "legacy"
word: "legacy"
first_encounter: "2026-09-09T10:30:00Z"
last_review: "2026-09-15T14:20:00Z"
next_review: "2026-09-18T14:20:00Z"
review_count: 3
error_count: 1
consecutive_correct: 2
mastery_level: 2
assessment_history:
  - timestamp: "2026-09-09T10:30:00Z"
    question_type: "mcq"
    question_content: "Which word means 'something that is the result of events in the past'?"
    user_response: "legacy"
    correct_answer: "legacy"
    correct: true
    time_spent: 8
  - timestamp: "2026-09-10T11:00:00Z"
    question_type: "fill_blank"
    question_content: "The war left a painful ________ of social division."
    user_response: "legacy"
    correct_answer: "legacy"
    correct: true
    time_spent: 5
  - timestamp: "2026-09-12T09:15:00Z"
    question_type: "short_answer"
    question_content: "Explain the difference between 'legacy' and 'heritage'."
    user_response: "Legacy is more about consequences of past events, heritage is shared culture."
    correct_answer: "Legacy refers to consequences/results of past events (can include property); heritage refers to shared cultural traditions."
    correct: false
    time_spent: 45
```

**DP-FORMAT-002**: All timestamps MUST use ISO 8601 format in UTC timezone.

### 4.3 Progress Summary File Format

**DP-SUMMARY-001**: `progress_summary.json` MUST contain:

```json
{
  "last_updated": "2026-09-15T14:20:00Z",
  "total_words": 150,
  "mastered_words": 23,
  "in_review_words": 87,
  "not_started_words": 40,
  "due_for_review": 15,
  "average_mastery_level": 2.3,
  "total_reviews_completed": 450,
  "total_errors": 78,
  "overall_accuracy": 0.827,
  "learning_streak_days": 12,
  "words_by_mastery_level": {
    "0": 40,
    "1": 25,
    "2": 30,
    "3": 22,
    "4": 20,
    "5": 13
  },
  "daily_activity": [
    {
      "date": "2026-09-15",
      "reviews_completed": 18,
      "new_words_learned": 3,
      "time_spent_minutes": 45
    }
  ]
}
```

### 4.4 Backup Strategy

**DP-BACKUP-001**: The system MUST create automatic backups:
- Before any write operation that modifies existing data
- Once per day at the end of the first session
- When explicitly requested by user

**DP-BACKUP-002**: Backups MUST be stored in `.memoria/learning_records/backup/{timestamp}/`

**DP-BACKUP-003**: The system MUST retain:
- Last 7 daily backups
- Last 4 weekly backups (every Sunday)
- Last 6 monthly backups (first day of month)

**DP-BACKUP-004**: Older backups beyond retention policy MUST be automatically deleted.

### 4.5 Data Validation

**DP-VAL-001**: On load, the system MUST validate:
- YAML syntax correctness
- Required fields presence
- Timestamp format validity
- Value range constraints (e.g., `mastery_level` in [0, 5])

**DP-VAL-002**: If validation fails:
- Log warning with file path and error details
- Attempt to recover with safe defaults
- If recovery impossible, skip the record and notify user

### 4.6 Concurrent Access

**DP-CONCUR-001**: The system MUST use file-level locking to prevent concurrent write conflicts.

**DP-CONCUR-002**: Lock acquisition timeout MUST be 5 seconds, after which operation fails with error.

---

## 5. Question Generation Specifications

### 5.1 MCQ Generation from Vocabulary Entries

**QG-MCQ-001**: Generate definition-based MCQ:

**Input**: Vocabulary entry for "legacy"

**Process**:
1. Extract core definition: "something that is the result of events in the past"
2. Create question: "Which word means 'something that is the result of events in the past'?"
3. Correct answer: "legacy"
4. Generate distractors from:
   - Confusion matrix words: "heritage", "inheritance"
   - Semantically related learned words: "tradition", "history"

**Output**:
```
Which word means 'something that is the result of events in the past'?
A) heritage
B) legacy
C) tradition
D) inheritance
```

**QG-MCQ-002**: Generate collocation-based MCQ:

**Input**: Collocation table for "legacy"

**Process**:
1. Select high-frequency collocation: "leave a legacy"
2. Create context sentence from example or generate new one
3. Create question testing appropriate collocation
4. Generate distractors using wrong prepositions/verbs

**Output**:
```
Complete the sentence: Great leaders strive to ________ a positive legacy.
A) make
B) leave
C) give
D) create
```

**QG-MCQ-003**: Generate nuance-distinction MCQ:

**Input**: Confusion matrix comparing "legacy", "heritage", "inheritance"

**Process**:
1. Extract distinguishing features from confusion matrix
2. Create scenario requiring precise word choice
3. Use all confused words as options

**Output**:
```
The war left a painful ________ of social division. (Choose the word emphasizing *consequences of past events*)
A) heritage
B) inheritance
C) legacy
D) tradition
```

### 5.2 Short Answer Generation

**QG-SA-001**: Generate definition recall questions:

```
Question: What does "legacy" mean in English? (provide definition in Chinese)
Expected answer format: 历史遗留产物；遗产，精神文化遗产
Evaluation: Accept answers containing key concepts (历史, 遗产, 遗留)
```

**QG-SA-002**: Generate collocation completion:

```
Question: Complete the collocation: ________ legacy (adjective + noun, meaning "painful historical consequences")
Expected answer: painful
Evaluation: Exact match or synonyms (traumatic, difficult)
```

**QG-SA-003**: Generate nuance explanation:

```
Question: Explain the difference between "legacy" and "heritage" in 1-2 sentences.
Expected answer: Legacy refers to consequences/results of past events (can be tangible property or abstract influence); heritage refers to shared cultural traditions belonging to a group (rarely refers to money).
Evaluation: Must mention consequence/result aspect of legacy AND cultural/shared aspect of heritage
```

### 5.3 Fill-in-Blank Generation

**QG-FB-001**: Generate from collocation examples:

**Input**: Collocation example: "The war left a painful legacy of social division."

**Process**:
1. Identify target word position
2. Determine if single word or phrase
3. Generate blank with type indicator
4. Provide Chinese translation hint

**Output**:
```
The war left a painful ________ of social division.
(这场战争给该地区留下了社会分裂的痛苦遗留问题。)
Type: [WORD]
Answer: legacy
```

**QG-FB-002**: Generate from writing examples:

**Input**: Writing example: "Much of the museum's collection came from private legacies donated by wealthy families."

**Output**:
```
Much of the museum's collection came from private ________ donated by wealthy families.
(博物馆大量藏品来自富裕家族捐赠的私人遗赠。)
Type: [WORD]
Answer: legacies
```

**QG-FB-003**: Generate multi-word phrase blanks:

**Input**: Collocation: "leave a legacy"

**Output**:
```
Great leaders strive to ________ for future generations.
(伟大的领导者力求为后代留下积极的精神遗产。)
Type: [PHRASE]
Answer: leave a positive legacy
```

### 5.4 Controlled Vocabulary Constraint

**QG-VOCAB-001**: For fill-in-blank generation, the system MUST:
1. Query learning records to get list of words with `mastery_level >= 1`
2. Only generate blanks for words in this list
3. If target word not yet learned, defer question generation

**QG-VOCAB-002**: The system MUST track question difficulty:
- Easy: Word with `mastery_level >= 3`, common collocation
- Medium: Word with `mastery_level >= 2`, less common usage
- Hard: Word with `mastery_level == 1`, nuanced distinction required

---

## 6. Integration with Existing Vocabulary Format

### 6.1 Vocabulary Entry Parsing

**INT-PARSE-001**: The system MUST parse vocabulary files in the format defined by `vocab_format.md`.

**INT-PARSE-002**: Parsing MUST extract:

| Section | Data Extracted | Used For |
|---------|----------------|----------|
| `## 🔉 Pronunciation & Listening Cue` | IPA, stress, listening traps | Pronunciation drills (future) |
| `## 📖 Core Definitions` | Definitions, dictionary source, speaking/writing examples | MCQ, short answer, context generation |
| `## 🧩 Word Family & Collocation Matrix` | Collocations table, word family table | MCQ, fill-in-blank, collocation testing |
| `## ⚔️ Confusion Matrix` | Near-synonyms, nuance distinctions | MCQ distractors, nuance questions |
| `## 🎯 Active Output Drills` | Gap-fill, speaking/writing scenarios | Direct question reuse, scenario testing |
| `## 📌 Revision Tags` | Tags | Categorization, filtering |

**INT-PARSE-003**: The system MUST handle missing sections gracefully:
- If pronunciation section missing: skip pronunciation-based questions
- If confusion matrix missing: use semantic similarity from other sources for distractors
- If active drills missing: generate drills from definitions and collocations

### 6.2 Vocabulary File Discovery

**INT-DISC-001**: The system MUST discover vocabulary files by:
1. Scanning the designated vocabulary directory (configurable)
2. Identifying Markdown files matching the vocabulary format
3. Extracting `word_id` from filename or first heading

**INT-DISC-002**: Default vocabulary directory: `/vocab`

### 6.3 Vocabulary Library Updates

**INT-UPDATE-001**: When new vocabulary files are added:
- System MUST detect new files on next startup or manual refresh
- System MUST initialize learning records for new words
- System MUST update vocabulary index

**INT-UPDATE-002**: When vocabulary files are modified:
- System MUST detect changes and re-parse
- System MUST preserve existing learning records
- System MUST update question bank with new content

---

## 7. User Interface Requirements

### 7.1 Learning Mode

**UI-LEARN-001**: When user selects a word to learn, display:
- Complete vocabulary entry (pronunciation, definitions, collocations, examples)
- Focus on active output sections (speaking/writing examples, drills)
- Highlight usage patterns and common pitfalls

**UI-LEARN-002**: After presenting content, prompt user:
```
You have learned "legacy". 
First review scheduled for: 2026-09-10 10:30 AM
Would you like to:
1) Practice now with a quiz
2) Continue to next word
3) Return to vocabulary list
```

### 7.2 Review Mode

**UI-REVIEW-001**: Display review dashboard:
```
=== Review Dashboard ===
Due for review today: 15 words
Overdue: 3 words
Mastered vocabulary: 23 words
Current learning streak: 12 days

[Start Review Session]
```

**UI-REVIEW-002**: During review session:
- Present questions one at a time
- Show question type indicator (MCQ / Short Answer / Fill-in-Blank)
- For fill-in-blank, clearly show [WORD] or [PHRASE] indicator
- Provide Chinese hints when appropriate
- Show timer (optional, can be disabled)

**UI-REVIEW-003**: After each question:
- Show immediate feedback (correct/incorrect)
- Display correct answer and explanation
- Show relevant vocabulary entry section for review
- Update learning record in real-time

**UI-REVIEW-004**: At end of session:
```
=== Session Complete ===
Questions answered: 15
Correct: 12 (80%)
Incorrect: 3 (20%)

Words needing attention:
- legacy (missed definition question)
- heritage (confused with legacy)
- inheritance (incorrect collocation)

[Review Missed Words] [Return to Dashboard]
```

### 7.3 Testing Mode

**UI-TEST-001**: Allow user to configure test:
- Number of questions (10, 20, 50, custom)
- Question type distribution (e.g., 40% MCQ, 30% short answer, 30% fill-blank)
- Difficulty level (easy, medium, hard, mixed)
- Time limit (optional)

**UI-TEST-002**: Display test with all questions at once or one-by-one (user preference).

**UI-TEST-003**: At end of test, provide detailed report:
- Overall score
- Performance by question type
- Performance by word
- Comparison to previous tests
- Recommended words to review

### 7.4 Analytics Mode

**UI-ANALYTICS-001**: Display progress charts:
- Vocabulary mastered over time (line chart)
- Mastery level distribution (bar chart)
- Error rate by word (sortable table)
- Review compliance (calendar heatmap)

**UI-ANALYTICS-002**: Provide drill-down capability:
- Click on word to see detailed learning history
- Click on date to see session details
- Filter by tag, mastery level, or date range

---

## 8. Error Handling Requirements

### 8.1 Missing Data

**EH-MISS-001**: If vocabulary file missing required section:
- Log warning: `[WARN] Vocabulary file {filename} missing section {section_name}`
- Skip questions dependent on that section
- Continue processing other sections

**EH-MISS-002**: If learning record file corrupted:
- Log error: `[ERROR] Learning record {word_id}.yaml is corrupted: {details}`
- Attempt to restore from most recent backup
- If restoration fails, initialize new record with safe defaults:
  - `first_encounter` = current timestamp
  - All counts = 0
  - `mastery_level` = 0
  - `next_review` = current timestamp + 1 day

**EH-MISS-003**: If `progress_summary.json` missing or corrupted:
- Rebuild from individual learning records
- Log: `[INFO] Rebuilt progress summary from learning records`

### 8.2 User Input Validation

**EH-INPUT-001**: For short answer questions:
- Trim whitespace
- Case-insensitive comparison (unless answer is proper noun)
- Accept synonyms/paraphrases if they capture key concepts
- If answer ambiguous, prompt for clarification

**EH-INPUT-002**: For fill-in-blank:
- Check if response is single word when `[WORD]` expected
- Check if response is multi-word when `[PHRASE]` expected
- Accept grammatically correct variations (e.g., singular/plural)

**EH-INPUT-003**: Invalid input handling:
- If user enters empty response, prompt: "Please provide an answer or skip this question."
- If user enters irrelevant text, mark as incorrect and show correct answer

### 8.3 System Failures

**EH-SYS-001**: If file write fails:
- Retry up to 3 times with exponential backoff (1s, 2s, 4s)
- If all retries fail, log error and notify user
- Preserve in-memory state to prevent data loss

**EH-SYS-002**: If backup creation fails:
- Log warning but do not block main operation
- Attempt backup again on next operation
- If backups consistently fail, notify user to check disk space/permissions

**EH-SYS-003**: If unexpected shutdown occurs:
- On next startup, check for incomplete operations
- Offer to recover unsaved progress if detected
- Validate all learning records for consistency

---

## 9. Performance Requirements

### 9.1 Response Time

**PERF-RT-001**: Question generation: < 1 second for standard assessments

**PERF-RT-002**: Learning record updates: < 500ms

**PERF-RT-003**: Progress report generation: < 3 seconds for 1000 entries

**PERF-RT-004**: Review queue calculation: < 2 seconds

**PERF-RT-005**: Vocabulary file parsing: < 100ms per file

### 9.2 Scalability

**PERF-SCALE-001**: Support vocabulary libraries of 1000+ entries without performance degradation.

**PERF-SCALE-002**: Use efficient data structures:
- Priority queue for review scheduling (O(log n) operations)
- Hash map for word lookup (O(1) average)
- Index for tag-based filtering

**PERF-SCALE-003**: Implement lazy loading:
- Load vocabulary entry content on demand
- Cache recently accessed entries
- Limit cache size to prevent memory bloat

**PERF-SCALE-004**: Batch write operations:
- Group multiple learning record updates
- Write to disk at end of session or every N updates

### 9.3 Resource Usage

**PERF-RES-001**: Memory usage: < 500MB for typical usage (100 words in active learning)

**PERF-RES-002**: Disk usage:
- Learning records: ~5KB per word
- Progress summary: < 100KB
- Backups: implement compression to reduce size

---

## 10. Security and Privacy

### 10.1 Data Privacy

**SEC-PRIV-001**: All learning data MUST be stored locally on user's machine.

**SEC-PRIV-002**: No learning data transmitted to external servers without explicit user consent.

**SEC-PRIV-003**: User MUST be able to export all learning data in portable format (JSON/CSV).

**SEC-PRIV-004**: User MUST be able to delete individual records or entire learning history.

### 10.2 Data Integrity

**SEC-INT-001**: Use file checksums to detect corruption.

**SEC-INT-002**: Validate data integrity on load.

**SEC-INT-003**: Maintain audit log of all write operations:
```
{timestamp} [WRITE] {file_path} {operation} {status}
```

---

## 11. Extension Points

### 11.1 Future Enhancements

**EXT-FUT-001**: Audio pronunciation playback
- Store audio file paths in vocabulary entries
- Integrate with audio player API
- Support both British and American pronunciations

**EXT-FUT-002**: Speech recognition for pronunciation practice
- Integrate with speech-to-text API
- Compare user pronunciation with IPA
- Provide feedback on accuracy

**EXT-FUT-003**: Writing sample evaluation
- Accept user-generated sentences using target vocabulary
- Automated feedback on grammar, collocation, appropriateness
- Integration with language model API for evaluation

**EXT-FUT-004**: Collaborative learning
- Share progress with study partners
- Leaderboards and challenges
- Peer review of writing samples

**EXT-FUT-005**: Mobile app synchronization
- Export learning records to mobile app
- Bidirectional sync with conflict resolution
- Offline mode with sync on reconnect

### 11.2 Customization Options

**EXT-CUSTOM-001**: User-configurable review intervals
- Allow users to adjust base intervals
- Maintain separate interval profiles (aggressive/balanced/relaxed)

**EXT-CUSTOM-002**: Custom weighting for question types
- Allow users to prefer certain question types
- Adjust difficulty distribution

**EXT-CUSTOM-003**: Personalized difficulty adjustment
- Track user performance patterns
- Dynamically adjust question difficulty to maintain optimal challenge level

**EXT-CUSTOM-004**: Custom tag-based filtering
- Allow users to create learning sessions by tag (e.g., "only IELTS Writing vocabulary")
- Support boolean tag queries (AND/OR/NOT)

---

## 12. Acceptance Criteria

The system meets requirements if:

**AC-001**: Learning records are accurately maintained and persist across sessions with no data loss.

**AC-002**: Review scheduling follows spaced repetition principles with intervals matching the algorithm specification in §3.

**AC-003**: Three types of assessments (MCQ, short answer, fill-in-blank) are correctly generated from vocabulary entries.

**AC-004**: Fill-in-blank exercises only use vocabulary the user has previously learned (verified through learning records).

**AC-005**: User progress is measurable through analytics dashboard showing mastery levels, error rates, and learning trends.

**AC-006**: Error patterns are identified and reflected in review prioritization.

**AC-007**: System handles 1000+ vocabulary entries without performance degradation (response times within specified limits).

**AC-008**: All data is stored locally with backup/recovery capability.

**AC-009**: System gracefully handles missing data, corrupted files, and unexpected shutdowns without data loss.

**AC-010**: User can export and delete learning data at any time.

---

**Document Version**: 1.0  
**Last Updated**: 2026-09-09  
**Status**: Initial Requirements Specification  
**Related Documents**: `agent_specification.md`, `vocab_format.md`
