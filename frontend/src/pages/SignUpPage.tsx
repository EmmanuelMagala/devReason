import { SignUp } from "@clerk/clerk-react";

export function SignUpPage() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <SignUp
        path="/sign-up"
        routing="path"
        signInUrl="/sign-in"
        afterSignUpUrl="/"
      />
    </div>
  );
}
