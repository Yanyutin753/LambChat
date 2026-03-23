/**
 * Project management hook for sidebar
 */

import { useState, useCallback } from "react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { projectApi, sessionApi } from "../services/api";
import type { Project } from "../types";

interface UseProjectManagerReturn {
  projects: Project[];
  loadProjects: () => Promise<void>;
  newProjectName: string;
  setNewProjectName: (name: string) => void;
  newProjectIcon: string;
  setNewProjectIcon: (icon: string) => void;
  showNewProjectModal: boolean;
  setShowNewProjectModal: (show: boolean) => void;
  handleCreateProject: () => Promise<void>;
  handleRenameProject: (projectId: string, name: string) => void;
  handleDeleteProject: (
    projectId: string,
    onAfter?: () => void,
  ) => Promise<void>;
  handleUpdateIcon: (projectId: string, icon: string) => Promise<void>;
  handleMoveSession: (
    sessionId: string,
    projectId: string | null,
  ) => Promise<void>;
}

export function useProjectManager(): UseProjectManagerReturn {
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectIcon, setNewProjectIcon] = useState("📁");
  const [showNewProjectModal, setShowNewProjectModal] = useState(false);

  const loadProjects = useCallback(async () => {
    try {
      const projectList = await projectApi.list();
      setProjects(projectList);
    } catch (err) {
      console.error("Failed to load projects:", err);
    }
  }, []);

  const handleCreateProject = async () => {
    const trimmedName = newProjectName.trim();
    if (!trimmedName) return;

    try {
      const newProject = await projectApi.create({
        name: trimmedName,
        icon: newProjectIcon || undefined,
      });
      setProjects((prev) => [...prev, newProject]);
      setNewProjectName("");
      setNewProjectIcon("📁");
      toast.success(t("sidebar.projectCreated"));
    } catch (err) {
      console.error("Failed to create project:", err);
      toast.error(t("sidebar.projectCreateFailed"));
    }
  };

  const handleRenameProject = (projectId: string, name: string) => {
    setProjects((prev) =>
      prev.map((p) => (p.id === projectId ? { ...p, name } : p)),
    );
  };

  const handleDeleteProject = async (
    projectId: string,
    onAfter?: () => void,
  ) => {
    try {
      await projectApi.delete(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
      onAfter?.();
      toast.success(t("sidebar.projectDeleted"));
    } catch (err) {
      console.error("Failed to delete project:", err);
      toast.error(t("sidebar.projectDeleteFailed"));
    }
  };

  const handleMoveSession = async (
    sessionId: string,
    projectId: string | null,
  ) => {
    try {
      const response = await sessionApi.moveToProject(sessionId, projectId);
      if (response.session) {
        toast.success(
          projectId ? t("sidebar.sessionMoved") : t("sidebar.sessionRemoved"),
        );
      }
    } catch (err) {
      console.error("Failed to move session:", err);
      toast.error(t("sidebar.sessionMoveFailed"));
    }
  };

  const handleUpdateIcon = async (projectId: string, icon: string) => {
    try {
      const updated = await projectApi.update(projectId, { icon });
      setProjects((prev) =>
        prev.map((p) =>
          p.id === projectId ? { ...p, icon: updated.icon } : p,
        ),
      );
    } catch (err) {
      console.error("Failed to update icon:", err);
      toast.error(t("sidebar.iconUpdateFailed"));
    }
  };

  return {
    projects,
    loadProjects,
    newProjectName,
    setNewProjectName,
    newProjectIcon,
    setNewProjectIcon,
    showNewProjectModal,
    setShowNewProjectModal,
    handleCreateProject,
    handleRenameProject,
    handleDeleteProject,
    handleMoveSession,
    handleUpdateIcon,
  };
}
