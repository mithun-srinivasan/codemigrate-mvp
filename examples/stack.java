public class Stack {
    private int[] data;
    private int top;

    public Stack(int capacity) {
        data = new int[capacity];
        top = -1;
    }

    public void push(int value) {
        if (top == data.length - 1) {
            throw new IllegalStateException("Stack is full");
        }
        data[++top] = value;
    }

    public int pop() {
        if (top < 0) {
            throw new IllegalStateException("Stack is empty");
        }
        return data[top--];
    }

    public boolean isEmpty() {
        return top < 0;
    }
}
