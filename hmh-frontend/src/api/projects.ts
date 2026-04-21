import client from "./client";

// Mirrors app/models/enums.py ProjectStatus
export type ProjectStatus = "PLANNED" | "ACTIVE" | "PAUSED" | "COMPLETED";

export interface Project {
  id: string;
  name: string;
  code: string;
  description: string | null;
  location: string | null;
  client_name: string | null;
  start_date: string | null;
  estimated_end_date: string | null;
  go_live_date: string | null;
  status: ProjectStatus;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  code: string;
  description?: string | null;
  location?: string | null;
  client_name?: string | null;
  start_date?: string | null;
  estimated_end_date?: string | null;
  go_live_date?: string | null;
  status?: ProjectStatus;
}

export interface ProjectUpdate {
  name?: string;
  code?: string;
  description?: string | null;
  location?: string | null;
  client_name?: string | null;
  start_date?: string | null;
  estimated_end_date?: string | null;
  go_live_date?: string | null;
  status?: ProjectStatus;
}

export interface PaginatedProjects {
  items: Project[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export const projectsApi = {
  list: async (page = 1, limit = 100, status?: ProjectStatus): Promise<PaginatedProjects> => {
    const params: Record<string, string | number> = { page, limit };
    if (status) params.status = status;
    const res = await client.get<{ data: PaginatedProjects }>("/projects/", { params });
    return res.data.data;
  },

  get: async (id: string): Promise<Project> => {
    const res = await client.get<{ data: Project }>(`/projects/${id}`);
    return res.data.data;
  },

  create: async (body: ProjectCreate): Promise<Project> => {
    const res = await client.post<{ data: Project }>("/projects/", body);
    return res.data.data;
  },

  update: async (id: string, body: ProjectUpdate): Promise<Project> => {
    const res = await client.patch<{ data: Project }>(`/projects/${id}`, body);
    return res.data.data;
  },
};
