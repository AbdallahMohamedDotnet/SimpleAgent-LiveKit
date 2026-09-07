CREATE TABLE `deep_dive_turns` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`interview_id` text NOT NULL,
	`seq` integer NOT NULL,
	`question` text NOT NULL,
	`answer` text NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`interview_id`) REFERENCES `interviews`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `deep_dive_turns_interview_seq_idx` ON `deep_dive_turns` (`interview_id`,`seq`);--> statement-breakpoint
CREATE TABLE `interviews` (
	`id` text PRIMARY KEY NOT NULL,
	`room_name` text NOT NULL,
	`participant_identity` text,
	`status` text DEFAULT 'in_progress' NOT NULL,
	`full_name` text,
	`age` integer,
	`job_title` text,
	`job_description` text,
	`domain` text,
	`seniority` text,
	`technologies` text,
	`probe_plan` text,
	`deep_dive_summary` text,
	`started_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	`completed_at` integer
);
--> statement-breakpoint
CREATE INDEX `interviews_room_name_idx` ON `interviews` (`room_name`);--> statement-breakpoint
CREATE TABLE `transcript_turns` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`interview_id` text NOT NULL,
	`seq` integer NOT NULL,
	`role` text NOT NULL,
	`text` text NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`interview_id`) REFERENCES `interviews`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `transcript_turns_interview_seq_idx` ON `transcript_turns` (`interview_id`,`seq`);