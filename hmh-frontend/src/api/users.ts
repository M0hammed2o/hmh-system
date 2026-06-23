import client from "./client";

export type UserRole = "OWNER" | "OFFICE_ADMIN" | "OFFICE_USER" | "PROCUREMENT_LEAD" | "SITE_MANAGER" | "SITE_MANAGER_VIEW" | "SITE_STAFF" | "READ_ONLY";

export const SITE_REQUIRING_ROLES: ReadonlySet<UserRole> = new Set(["SITE_MANAGER", "SITE_MANAGER_VIEW", "SITE_STAFF"]);

export interface User {
  id: string;
  full_name: string;
  email: string;
  phone: string | null;
  role: UserRole;
  is_active: boolean;
  must_reset_password: boolean;
  last_login_at: string | null;
  failed_login_attempts: number;
  locked_until: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  project_access_count: number;
}

export interface UserCreate {
  full_name: string;
  email: string;
  phone?: string;
  role: UserRole;
  project_ids?: string[];
}

export interface UserUpdate {
  full_name?: string;
  phone?: string;
  role?: UserRole;
  is_active?: boolean;
}

export interface PaginatedUsers {
  items: User[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface UserProjectAccess {
  id: string;
  user_id: string;
  project_id: string;
  can_view: boolean;
  can_edit: boolean;
  can_approve: boolean;
  created_at: string;
}

export const usersApi = {
  me: async (): Promise<User> => {
    const res = await client.get<{ data: User }>("/users/me");
    return res.data.data;
  },

  list: async (page = 1, limit = 20): Promise<PaginatedUsers> => {
    const res = await client.get<{ data: PaginatedUsers }>("/users/", { params: { page, limit } });
    return res.data.data;
  },

  create: async (body: UserCreate): Promise<{ user: User; temp_password: string }> => {
    const res = await client.post<{ data: User & { temp_password: string } }>("/users/", body);
    return { user: res.data.data, temp_password: res.data.data.temp_password };
  },

  update: async (id: string, body: UserUpdate): Promise<User> => {
    const res = await client.patch<{ data: User }>(`/users/${id}`, body);
    return res.data.data;
  },

  deactivate: async (id: string): Promise<User> => {
    const res = await client.delete<{ data: User }>(`/users/${id}`);
    return res.data.data;
  },

  resetPassword: async (id: string): Promise<{ user: User; temp_password: string }> => {
    const res = await client.post<{ data: User & { temp_password: string } }>(`/users/${id}/reset-password`);
    return { user: res.data.data, temp_password: res.data.data.temp_password };
  },

  deleteUser: async (id: string): Promise<void> => {
    await client.delete(`/users/${id}/delete`);
  },

  unlockUser: async (id: string): Promise<User> => {
    const res = await client.post<{ data: User }>(`/users/${id}/unlock`);
    return res.data.data;
  },

  reactivateUser: async (id: string): Promise<User> => {
    const res = await client.post<{ data: User }>(`/users/${id}/reactivate`);
    return res.data.data;
  },

  setPin: async (id: string, pin: string): Promise<User> => {
    const res = await client.post<{ data: User }>(`/users/${id}/set-pin`, { pin });
    return res.data.data;
  },

  getProjectAccess: async (id: string): Promise<UserProjectAccess[]> => {
    const res = await client.get<{ data: UserProjectAccess[] }>(`/users/${id}/project-access`);
    return res.data.data;
  },

  grantProjectAccess: async (id: string, projectId: string): Promise<UserProjectAccess> => {
    const res = await client.post<{ data: UserProjectAccess }>(`/users/${id}/project-access`, {
      project_id: projectId,
      can_view: true,
      can_edit: false,
      can_approve: false,
    });
    return res.data.data;
  },

  revokeProjectAccess: async (id: string, projectId: string): Promise<void> => {
    await client.delete(`/users/${id}/project-access/${projectId}`);
  },
};
