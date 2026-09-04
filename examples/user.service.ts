import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

export interface User {
  id: number;
  name: string;
}

@Injectable({ providedIn: 'root' })
export class UserService {
  constructor(private http: HttpClient) {}

  getNames(): Observable<string[]> {
    return this.http.get<User[]>('/api/users').pipe(
      map(users => users.map(u => u.name))
    );
  }
}
