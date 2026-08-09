import { createCommand } from "lexical";
import type {
  FileReferenceDescriptor,
  FileReferenceStatus,
  SkillReferenceDescriptor,
} from "../composerTypes";

export const INSERT_FILE_REFERENCE_COMMAND =
  createCommand<FileReferenceDescriptor>("INSERT_FILE_REFERENCE_COMMAND");

export const INSERT_SKILL_REFERENCE_COMMAND =
  createCommand<SkillReferenceDescriptor>("INSERT_SKILL_REFERENCE_COMMAND");

export const REMOVE_FILE_REFERENCE_COMMAND = createCommand<string>(
  "REMOVE_FILE_REFERENCE_COMMAND",
);

export const UPDATE_FILE_REFERENCE_COMMAND = createCommand<{
  referenceId: string;
  status: FileReferenceStatus;
  fileName?: string;
}>("UPDATE_FILE_REFERENCE_COMMAND");
