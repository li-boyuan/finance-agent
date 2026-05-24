import { NextResponse, type NextRequest } from "next/server";

// Lightweight auth check: just verify a Supabase auth cookie is present.
// Real JWT validation happens on the backend (app/api/deps.py) for every
// authenticated request, so this middleware only needs to prevent obvious
// drive-bys to /dashboard.
//
// We intentionally do NOT call supabase.auth.getUser() here because that
// makes a network request to Supabase from the Node runtime, which is
// blocked on some networks (e.g., Meta corp policy returns EPERM on the
// connect() syscall to non-allowlisted hosts).

export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname.startsWith("/dashboard")) {
    const hasAuthCookie = request.cookies
      .getAll()
      .some(
        (c) => c.name.startsWith("sb-") && c.name.endsWith("-auth-token"),
      );
    if (!hasAuthCookie) {
      const url = request.nextUrl.clone();
      url.pathname = "/login";
      return NextResponse.redirect(url);
    }
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
