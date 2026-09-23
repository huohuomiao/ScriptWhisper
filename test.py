if(l1==nullptr) {
    return l2;
}else if(l2=nullptr){
    return l1;
}else if(l1.val>l2.val){
    l2->next=merge(l2->next,l1);
    return l2;
}else{
    l1->next=merge(l1->next,l2);
    return l1;
}