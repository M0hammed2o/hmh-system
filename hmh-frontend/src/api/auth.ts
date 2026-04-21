import client from "./client";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  must_reset_password: boolean;
}

export const authApi = {
  login: async (body: LoginRequest): Promise<TokenResponse> => {
    const res = await client.post<TokenResponse>("/auth/login", body);
    return res.data;
  },

  changePassword: async (current_password: string, new_password: string): Promise<void> => {
    await client.post("/auth/change-password", { current_password, new_password });
  },
};
