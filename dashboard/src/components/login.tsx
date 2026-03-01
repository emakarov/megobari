import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface LoginProps {
  onLogin: () => void;
}

export function Login({ onLogin }: LoginProps) {
  const [token, setTokenValue] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showToken, setShowToken] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      setToken(token);
      const res = await fetch("/api/health", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (res.status === 401) {
        setError("Invalid token");
        setLoading(false);
        return;
      }

      if (!res.ok) {
        setError(`Server error: ${res.status}`);
        setLoading(false);
        return;
      }

      onLogin();
    } catch {
      setError("Cannot connect to server");
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground text-lg font-bold">
            M
          </div>
          <CardTitle>Megobari Dashboard</CardTitle>
          <CardDescription>Enter your dashboard token to continue</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="relative">
              <Input
                type={showToken ? "text" : "password"}
                placeholder="Dashboard token"
                value={token}
                onChange={(e) => setTokenValue(e.target.value)}
                autoFocus
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                tabIndex={-1}
              >
                {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={!token || loading}>
              {loading ? "Connecting..." : "Sign In"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
