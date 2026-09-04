import { Component, Input, Output, EventEmitter } from '@angular/core';

@Component({
  selector: 'app-todo-item',
  template: `
    <div class="todo-item" [class.done]="todo.done">
      <input type="checkbox" [checked]="todo.done" (change)="toggle.emit(todo)" />
      <span>{{ todo.title }}</span>
    </div>
  `
})
export class TodoItemComponent {
  @Input() todo: { title: string; done: boolean };
  @Output() toggle = new EventEmitter();
}
