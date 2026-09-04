import { Component } from '@angular/core';
import { FormBuilder, Validators } from '@angular/forms';

@Component({
  selector: 'app-login-form',
  template: `
    <form [formGroup]="form" (ngSubmit)="submit()">
      <input formControlName="email" type="email" />
      <input formControlName="password" type="password" />
      <button type="submit" [disabled]="form.invalid">Login</button>
    </form>
  `
})
export class LoginFormComponent {
  form = this.fb.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
  });

  constructor(private fb: FormBuilder) {}

  submit() {
    if (this.form.invalid) return;
    console.log(this.form.value);
  }
}
