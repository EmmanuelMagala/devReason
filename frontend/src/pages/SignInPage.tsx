import { SignIn } from "@clerk/clerk-react";

export function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <SignIn
        path="/sign-in"
        routing="path"
        signUpUrl="/sign-up"
        afterSignInUrl="/"
      />
    </div>
  );
}
