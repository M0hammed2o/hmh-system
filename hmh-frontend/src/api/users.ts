import client from "./client";

export type UserRole = "OWNER" | "OFFICE_ADMIN" | "OFFICE_USER" | "SITE_MANAGER" | "SITE_STAFF";

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
}

export interface UserCreate {
  full_name: string;
  email: string;
  phone?: string;
  role: UserRole;
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
};
