# Penn tool inventory

All live writes are blocked in the testing deployment. Write handlers have simulated coverage only; none are live-tested.

| Tool | Access | Purpose |
| --- | --- | --- |
| `get_self` | Read | Read the signed-in Penn Canvas identity. |
| `list_courses` | Read | List my active courses. |
| `get_course_details` | Read | Read a course and my enrollment. |
| `get_syllabus` | Read | Read the complete course syllabus. |
| `list_assignments` | Read | List assignments, including my submissions. |
| `get_assignment_details` | Read | Read assignment details and rubric. |
| `get_rubric` | Read | Read the rubric embedded in an assignment. |
| `get_my_submission` | Read | Read my submission, grade, rubric assessment and feedback. |
| `list_modules` | Read | List course modules. |
| `list_module_items` | Read | List items in one module. |
| `list_pages` | Read | List course pages. |
| `get_page_content` | Read | Read a full course page. |
| `get_front_page` | Read | Read the course front page. |
| `list_course_files` | Read | List course file metadata. |
| `get_file` | Read | Read file metadata and Canvas download link. |
| `list_folders` | Read | List course folders. |
| `list_files_in_folder` | Read | List files in a folder. |
| `list_quizzes` | Read | List Classic Quizzes. New Quizzes may appear only as assignments. |
| `get_quiz_details` | Read | Read Classic Quiz details permitted by Canvas. |
| `get_quiz_questions` | Read | Read quiz questions only if Canvas permits access. |
| `get_quiz_submission_questions` | Read | Read questions for my existing quiz submission; never starts an attempt. |
| `list_discussion_topics` | Read | List course discussion topics. |
| `get_discussion_topic_details` | Read | Read full topic content. |
| `list_discussion_entries` | Read | Read top-level discussion entries. |
| `get_discussion_with_replies` | Read | Read the complete discussion view and replies. |
| `list_announcements` | Read | List course announcements. |
| `list_conversations` | Read | List my inbox without changing read state. |
| `get_conversation_details` | Read | Read a conversation without marking it read. |
| `get_unread_count` | Read | Read inbox unread count. |
| `find_message_recipients` | Read | Find message recipients in a course. |
| `get_my_course_grades` | Read | Read my course grades, never a roster. |
| `get_my_assignment_scores` | Read | Read my complete per-assignment scores. |
| `get_assignment_groups` | Read | Read weighting and drop rules for grade interpretation. |
| `list_calendar_events` | Read | Read events in a bounded date range. |
| `get_calendar_event` | Read | Read a calendar event. |
| `get_my_todo_items` | Read | Read Canvas to-dos. |
| `get_my_upcoming_assignments` | Read | Read upcoming Canvas events. |
| `list_planner_notes` | Read | Read my planner notes. |
| `get_my_peer_reviews_todo` | Read | Read my assigned peer reviews through the planner. |
| `list_my_peer_reviews` | Read | Read peer reviews assigned to me. |
| `post_discussion_entry` | Write — live-untested | Post an explicitly authorized discussion entry. |
| `reply_to_discussion_entry` | Write — live-untested | Reply to a discussion entry. |
| `send_message` | Write — live-untested | Send a message to explicit numeric recipients, maximum five. |
| `reply_to_conversation` | Write — live-untested | Reply to an existing inbox conversation. |
| `mark_conversation_read` | Write — live-untested | Mark one conversation read. |
| `create_planner_note` | Write — live-untested | Create a personal planner note. |
| `update_planner_note` | Write — live-untested | Update a personal planner note. |
| `delete_planner_note` | Write — live-untested | Delete a personal planner note. |
| `mark_planner_item_complete` | Write — live-untested | Mark a planner item complete. |
| `create_personal_calendar_event` | Write — live-untested | Create a calendar event in my own user calendar. |
| `delete_personal_calendar_event` | Write — live-untested | Delete my own personal calendar event. |
| `comment_on_my_submission` | Write — live-untested | Add a comment to my submission. |
| `submit_assignment` | Write — live-untested | Submit text to an assignment. Live behavior untested. |
| `mark_module_item_done` | Write — live-untested | Mark one module item done. |
| `list_my_announcements` | Read | List announcements across explicitly selected course IDs. |
| `get_my_activity_stream` | Read | Read my activity stream without marking items read. |
| `get_discussion_entry_details` | Read | Read replies to one discussion entry. |
| `start_quiz_submission` | Write — live-untested | Start an explicitly authorized Classic Quiz attempt; consumes an attempt. Live-untested. |
| `answer_quiz_questions` | Write — live-untested | Save authorized answers to my existing attempt; no synthetic events. |
| `complete_quiz_submission` | Write — live-untested | Complete my explicitly authorized attempt; never automatically retried. |
| `comment_on_peer_review` | Write — live-untested | Comment only on a submission assigned to me for review. |
| `submit_url_assignment` | Write — live-untested | Submit an explicitly authorized URL to an assignment. Live-untested. |
| `submit_assignment_files` | Write — live-untested | Submit files already uploaded to Canvas. Live-untested. |
| `submit_peer_review_rubric` | Write — live-untested | Submit a rubric assessment for a peer review assigned to me. Live-untested. |
| `upload_submission_file` | Write — live-untested | Upload an inline file (up to 512 KiB) for an explicitly authorized assignment submission. Does not submit it. Live-untested. |
| `download_file` | Read | Read a bounded file, with scoped cookies and validated redirects. |
| `scan_canvas` | Read | Read-only cross-course plan. |
| `search_course_content` | Read | Accessible metadata and up to 25 page bodies; coverage is explicit. |
| `calculate_grade_scenarios` | Read | Local hypothetical calculation; never writes grades. |
| `search_canvas_tools` | Read | Search the tool manifest. |
| `get_session_status` | Read | Read sanitized recovery state. |

71 tools total: 49 reads/local operations and 22 writes. No educator or staff tools.

The API shapes are adapted from Canvas Pilot and the student capabilities reviewed in vishalsachdev/canvas-mcp at `8b08bd77f524097606052de70cb4c2e5944a0c16`. This is an explicit student registry, not a wholesale registration of the upstream server.
